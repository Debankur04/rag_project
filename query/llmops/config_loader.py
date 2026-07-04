from pathlib import Path

import yaml


def load_config(config_path: str | None = None) -> dict:
    path = Path(config_path) if config_path else Path(__file__).resolve().parents[2] / "config" / "config.yaml"
    with path.open("r") as file:
        config = yaml.safe_load(file)
        # print(config)
    return config
