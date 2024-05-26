# rg_configured_search
A ripgrep-based Python tool to quickly search all files in a folder for strings in a yaml config file, and write the matches to a well-organizer folder

## Example

```bash
pip install rg_configured_search
rg_configured_search -h
rg_configured_search -s ./test_data/ -o test_output/ -c ./test_data/sample_config_1.yaml
```

Running the above commands yields the following output structure:

```
├── Example Hex Needle
│   └── a70671_binary_test_1_bin
│       └── found_g_0x0000_0000_0f65_startat_0x0b65.bin
├── Example Needle 3
│   └── 1b1b4d_sample_config_1_yaml
│       └── found_g_0x0000_0000_0160_startat_0x0000.bin
├── matches.jsonl
├── searcher_info.log
├── searcher_verbose.log
└── Something
    ├── 1b1b4d_sample_config_1_yaml
    │   ├── found_g_0x0000_0000_0009_startat_0x0000.bin
    │   ├── found_g_0x0000_0000_001c_startat_0x0000.bin
    │   └── found_g_0x0000_0000_005a_startat_0x0000.bin
    ├── 4a9d78_test_data_inventory_md
    │   └── found_g_0x0000_0000_0049_startat_0x0000.bin
    └── a70671_binary_test_1_bin
        └── found_g_0x0000_0000_0cb7_startat_0x08b7.bin

8 directories, 10 files
```
