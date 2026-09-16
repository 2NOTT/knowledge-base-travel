from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv(override=True)


def get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class EmbeddingConfig:
    bge_m3_path: str | None
    bge_m3: str
    bge_device: str
    bge_fp16: bool


embedding_config = EmbeddingConfig(
    bge_m3_path=os.getenv("BGE_M3_PATH"),
    bge_m3=os.getenv("BGE_M3", "BAAI/bge-m3"),
    bge_device=os.getenv("BGE_DEVICE", "cpu"),
    bge_fp16=get_bool_env("BGE_FP16", default=False),
)