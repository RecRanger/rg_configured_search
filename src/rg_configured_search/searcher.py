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
    # "-a"/"--text" flag: "treat binary files as text" - required for \x00 byte
    results = (
        rg.byte_offset()
        .no_ignore()
        .text()
        .unrestricted()  # -uuu means "search EVERY file"
        .unrestricted()
        .unrestricted()
        .json()
        .run()
        .as_dict
    )

    logger.info(f"Search complete, found {len(results)} matches")
    logger.debug(json.dumps(results, indent=2))

    running_submatch_count = 0
    saved_to_file_count = 0
    # For each match, assign the match with the input SearchItem, and save the
    # match to a file (plus some bytes on each side of the match).
    for match_num, match in enumerate(results, 1):
        logger.debug(f"Raw match from ripgrep: {json.dumps(match)}")
        if match["type"] != "match":  # skip begin/end/summary, if they show up
            continue
        assert isinstance(match["data"]["submatches"], list)
        assert (
            submatch_count := len(match["data"]["submatches"]) >= 1
        ), f"Unexpected number of submatches: {submatch_count}"

        # Iterate through all submatches, because if there are multiple matches
        # found near each other, then they get sent as submatches.
        for submatch in match["data"]["submatches"]:
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
            ), f"Matched unexpected number of search items: {applicable_search_items=} != 1"  # noqa
            search_item = applicable_search_items[0]

            source_file_path = Path(match["data"]["path"]["text"])

            # dumb, but you have to add them together
            global_offset = (
                match["data"]["absolute_offset"] + submatch["start"]
            )

            # Hash the file path to get a unique identifier for the file
            # (not the best, but good enough)
            source_file_path_hash = _md5sum(str(source_file_path.absolute()))
            (
                directory := (
                    output_dir
                    / f"{search_item.happiness_level}_{search_item.name}"
                    / f"{source_file_path_hash}_{source_file_path.name.replace('.', '_')}"  # noqa
                )
            ).mkdir(parents=True, exist_ok=True)
            if search_item.write_to_file:
                save_match_to_file(
                    search_item=search_item,
                    source_file_path=source_file_path,
                    output_dir=directory,
                    global_offset=global_offset,
                )
                saved_to_file_count += 1

            # store data to a jsonl file
            match_log_summary = {
                "uuid": str(uuid.uuid4()),
                "search_item": search_item.as_dict,
                "source_file_path": str(source_file_path.absolute()),
                "global_offset": global_offset,
                "timestamp_utc": str(datetime.datetime.utcnow()),
            }
            match_log_summary_json = json.dumps(match_log_summary) + "\n"
            with open(output_dir / "matches.jsonl", "a") as f:
                f.write(match_log_summary_json)
            with open(directory / "matches.jsonl", "a") as f:
                f.write(match_log_summary_json)
            logger.info(
                f"Saved match {match_num:,}/{len(results):,} = "
                f"{match_num/len(results):.1%} "
                f"(submatch #{running_submatch_count:,}): "
                + json.dumps(match_log_summary)
            )
            running_submatch_count += 1

    logger.info(
        f"Reviewed all {running_submatch_count} matches. "
        f"Saved {saved_to_file_count:,} matches to files."
    )


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


def save_match_to_file(
    search_item: SearchItem,
    source_file_path: Path,
    output_dir: Path,
    global_offset: int,  # global offset of the start of the match
) -> None:
    """Save the match to a file in the specified output directory."""
    assert (
        search_item.write_to_file
    ), "Trying to write to file, but SearchItem has write_to_file disabled"

    # get the local_offset (number of bytes before the match)
    if global_offset < search_item.byte_count_before_match:
        # The offset is very close to the start of the file, so store from the
        # start of the file.
        byte_count_before_match = global_offset
    else:
        byte_count_before_match = search_item.byte_count_before_match

    start_global_offset = global_offset - byte_count_before_match
    assert start_global_offset >= 0
    end_global_offset = min(
        (
            global_offset
            + len(search_item.val_as_bytes)
            + search_item.byte_count_after_match
        ),
        source_file_path.stat().st_size,
    )
    length_of_output_bytes = end_global_offset - start_global_offset

    hex_global = _format_as_hex(global_offset, 12)  # 12 is good for 2 TiB
    hex_local = _format_as_hex(byte_count_before_match, 4)

    output_filename = f"found_g_0x{hex_global}_startat_0x{hex_local}.bin"
    output_path = output_dir / output_filename

    with open(source_file_path, "rb") as source_file:
        source_file.seek(start_global_offset)
        data_bytes = source_file.read(length_of_output_bytes)
    assert len(data_bytes) == length_of_output_bytes

    with open(output_path, "wb") as output_file:
        output_file.write(data_bytes)
