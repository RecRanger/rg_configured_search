from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import re

from functools import cached_property
import yaml


@dataclass
class SearchItem:
    name: str
    val: str
    val_format: str
    description_notes: str
    happiness_level: int
    write_to_file: bool = True
    byte_count_before_match: Optional[int] = 1024
    byte_count_after_match: Optional[int] = 1024

    @cached_property
    def val_as_bytes(self) -> bytes:

        if self.val_format == "ascii":
            return self.val.encode("utf-8")
        elif self.val_format == "hex":
            val = self.val.lower()
            val = re.sub(r"\s+", "", val)
            val = val.replace("0x", "")
            assert (
                len(val) % 2 == 0
            ), "Hex value must have an even number of characters"
            val = bytes.fromhex(val)
            return val
        else:
            raise ValueError(
                f"val_format must be 'ascii' or 'hex', not {self.val_format}"
            )

    @cached_property
    def clean_hex_pattern_searchable(self) -> str:
        """Return the lowercase hex value without any whitespace, with \\x prefixes."""  # noqa
        assert self.val_format in ["ascii", "hex"]
        val = self.val_as_bytes.hex()  # lowercase, no spaces
        pattern = "".join(
            ("\\x" + val[i : i + 2]) for i in range(0, len(val), 2)  # noqa
        )
        return pattern

    @cached_property
    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "val": self.val,
            "val_hex": self.val_as_bytes.hex(),
            "val_format": self.val_format,
            "description_notes": self.description_notes,
            "happiness_level": self.happiness_level,
            "write_to_file": self.write_to_file,
            "byte_count_before_match": self.byte_count_before_match,
            "byte_count_after_match": self.byte_count_after_match,
        }


def load_config(yaml_file: str | Path) -> list[SearchItem]:
    with open(yaml_file, "r") as file:
        config_data = yaml.safe_load(file)
    return [SearchItem(**item) for item in config_data]
