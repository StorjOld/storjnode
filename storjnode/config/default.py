import json


DEFAULT = json.loads(r"""
{
    "version": 1,
    "cold_storage": [],
    "network": {
        "port": "random",
        "bootstrap_nodes": [],
        "disable_data_transfer": false,
        "refresh_neighbours_interval": 0,
        "bandwidth_limits": {
            "sec": {
                "upstream": 0,
                "downstream": 0
            },
            "month": {
                "upstream": "5G",
                "downstream": "5G"
            }
        },
        "monitor": {
            "enable_crawler": true,
            "enable_responses": true,
            "crawler_limit": 20,
            "crawler_interval": 600
        }
    },
    "storage": {
        "~/.storj/store": {
            "limit": "5G",
            "use_folder_tree": false
        }
    }
}
""")
