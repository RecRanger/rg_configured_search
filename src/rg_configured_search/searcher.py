from pathlib import Path
import base64
import json
import datetime
from typing import List
import uuid
import hashlib

from loguru import logger
import ripgrepy

from rg_configured_search.config_reader import SearchItem


def _md5sum(input: str, length: int = 6) -> str:
    return hashlib.md5(input.encode()).hexdigest()[:length]


def search_and_save_all_files(
    search_items: List[SearchItem], search_dir: Path, output_dir: Path
) -> None:
    """Search for all patterns in a single file using ripgrep and save matches
    according to the config.
    """
    # Prepare the patterns for searching
    patterns = []
    for search_item in search_items:
        # Note: the following if-statement isn't even technically necessary
        #   because we could use the clean_hex_pattern_searchable property
        #   for both ASCII and HEX searches (less readable though).
        if search_item.val_format in ["ascii", "hex"]:
            # construct per https://github.com/BurntSushi/ripgrep/issues/2809
            # e.g., "(?-u:\\x01\\x02\\x03)"
            pattern = f"(?-u:{search_item.clean_hex_pattern_searchable})"
        # elif search_item.val_format == "ascii":
        #     pattern = f"({search_item.val})"  # ASCII format, used directly
        else:
            raise ValueError(f"Unsupported format: {search_item.val_format}")
        patterns.append(pattern)

    # Combine into a single regex pattern
    combined_pattern = "|".join(patterns)
    logger.debug(f"Combined pattern: {combined_pattern}")

    # Perform the search using ripgrep
    logger.info(f"Starting ripgrep search for {len(search_items)} patterns")
    rg = ripgrepy.Ripgrepy(
        regex_pattern=combined_pattern, path=str(search_dir.absolute())
    )
    # TODO: maybe add the "-a" flag equivalent ("treat binary files as text"??)
    results = rg.byte_offset().binary().no_ignore().json().run().as_dict

    logger.info(f"Search complete, found {len(results)} matches")
    logger.debug(json.dumps(results, indent=2))

    # For each match, assign the match with the input SearchItem, and save the
    # match to a file (plus some bytes on each side of the match).
    for match in results:
        logger.info(f"Raw match from ripgrep: {json.dumps(match)}")
        if match["type"] != "match":  # skip begin/end/summary, if they show up
            continue
        assert isinstance(match["data"]["submatches"], list)
        assert (
            submatch_count := len(match["data"]["submatches"]) == 1
        ), f"Unexpected number of submatches: {submatch_count}"
        submatch = match["data"]["submatches"][0]
        applicable_search_items = [
            item
            for item in search_items
            if (
                submatch["match"].get("text") == item.val
                or base64.b64decode(submatch["match"].get("bytes", ""))
                == item.val_as_bytes
                or submatch["match"].get("text", "").encode("utf-8")
                == item.val_as_bytes
            )
        ]
        assert (
            len(applicable_search_items) == 1
        ), f"Match matched multiple search items: {applicable_search_items}"
        search_item = applicable_search_items[0]

        source_file_path = Path(match["data"]["path"]["text"])

        # dumb, but you have to add them together
        global_offset = match["data"]["absolute_offset"] + submatch["start"]

        save_match(
            search_item=search_item,
            source_file_path=source_file_path,
            output_dir=output_dir,
            global_offset=global_offset,
        )

        # store data to a jsonl file
        match_log_summary = {
            "uuid": str(uuid.uuid4()),
            "search_item": search_item.as_dict,
            "source_file_path": str(source_file_path.absolute()),
            "global_offset": global_offset,
            "timestamp_utc": str(datetime.datetime.utcnow()),
        }
        with open(output_dir / "matches.jsonl", "a") as f:
            json.dump(match_log_summary, f)
            f.write("\n")
        logger.info(f"Saved match: {json.dumps(match_log_summary)}")

    logger.info(f"Saved {len(results)} matches to files.")


def _format_as_hex(value: int, width: int = 16) -> str:
    """Format an integer as a hex string with a specified width, with
    underscores every 4 characters.
    """
    fmt_val = format(value, f"0{width}x")
    if len(fmt_val) < 4:
        return fmt_val
    for i in range(len(fmt_val) - (len(fmt_val) % 4) - 4, 0, -4):
        fmt_val = fmt_val[:i] + "_" + fmt_val[i:]
    return fmt_val


def save_match(
    search_item: SearchItem,
    source_file_path: Path,
    output_dir: Path,
    global_offset: int,
) -> None:
    """Save the match to a file in the specified output directory."""
    # get the local_offset (number of bytes before the match)
    local_offset = max(global_offset - search_item.byte_count_before_match, 0)

    start_global_offset = global_offset - local_offset
    end_global_offset = min(
        (
            global_offset
            + len(search_item.val_as_bytes)
            + search_item.byte_count_after_match
        ),
        source_file_path.stat().st_size,
    )
    length_of_output_bytes = end_global_offset - start_global_offset

    # Hash the file path to get a unique identifier for the file (good enough)
    source_file_path_hash = _md5sum(str(source_file_path.absolute()))
    (
        directory := (
            output_dir
            / search_item.name
            / f"{source_file_path_hash}_{source_file_path.name.replace('.', '_')}"  # noqa
        )
    ).mkdir(parents=True, exist_ok=True)

    hex_global = _format_as_hex(global_offset, 12)  # 12 is good for 2 TiB
    hex_local = _format_as_hex(local_offset, 4)

    output_filename = f"found_g_0x{hex_global}_startat_0x{hex_local}.bin"
    output_path = directory / output_filename

    with open(source_file_path, "rb") as source_file:
        source_file.seek(start_global_offset)
        data_bytes = source_file.read(length_of_output_bytes)
    assert len(data_bytes) == length_of_output_bytes

    with open(output_path, "wb") as output_file:
        output_file.write(data_bytes)
