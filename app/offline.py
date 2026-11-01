"""Force fully-offline behaviour for every library that might phone home.

Imported first by app.main so these variables are set before
transformers / huggingface_hub are imported anywhere.
"""

import os

OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
    "TOKENIZERS_PARALLELISM": "false",
}


def enforce_offline() -> None:
    for key, value in OFFLINE_ENV.items():
        os.environ[key] = value


enforce_offline()
