import argparse
from pathlib import Path

from loguru import logger

from rg_configured_search.searcher import search_and_save_all_files
from rg_configured_search.config_reader import load_config


def main():
    parser = argparse.ArgumentParser(
        description="Search for patterns in files."
    )
    parser.add_argument(
        "-s",
        "--search-dir",
        dest="search_dir",
        required=True,
        type=Path,
        help="The directory to search for files.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        dest="output_dir",
        required=True,
        type=Path,
        help="The directory to save the output files.",
    )
    parser.add_argument(
        "-c",
        "--config-file",
        dest="config_file",
        required=True,
        type=Path,
        help="The YAML file containing the search patterns.",
    )
    args = parser.parse_args()

    logger.add(Path(args.output_dir) / "searcher_info.log", level="INFO")
    logger.add(Path(args.output_dir) / "searcher_verbose.log")

    logger.info(
        f"Searching {args.search_dir} for patterns in {args.config_file}"
    )
    logger.info(f"Saving output to {args.output_dir}")
    logger.info(f"Args: {args}")

    config = load_config(Path(args.config_file))
    search_and_save_all_files(
        config, Path(args.search_dir), Path(args.output_dir)
    )

    logger.info("Done!")


if __name__ == "__main__":
    main()
