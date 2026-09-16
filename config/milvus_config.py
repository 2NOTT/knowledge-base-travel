from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class MilvusConfig:
    milvus_url: str
    chunks_collection: str
    travel_entities_collection: str

# 实例化Milvus配置对象（和其他配置对象命名风格统一）
milvus_config = MilvusConfig(
    milvus_url=os.getenv("MILVUS_URL"),
    chunks_collection=os.getenv("CHUNKS_COLLECTION"),
    travel_entities_collection=os.getenv("TRAVEL_ENTITIES_COLLECTION")
)
