import json
import logging
from pathlib import Path

from processor.import_processor.base import BaseNode, setup_logging
from processor.import_processor.exceptions import StateFieldError, FileProcessingError, ValidationError
from processor.import_processor.state import ImportGraphState


class NodeEntry(BaseNode):
    """
    入口节点：任务分发
    """

    name = "node_entry"

    def process(self, state: ImportGraphState):
        # 判断文件的扩展名是pdf还是md
        # 如果是pdf则进入pdf处理节点

        # 1.从state中获取文件的绝对路径
        import_file_path = state.get("import_file_path")
        # 2.判断路径是否为空
        if not import_file_path:
            raise StateFieldError(
                field_name="import_file_path",
                message="文件路径不能为空",
                expected_type=str
            )

        # 2.将import_file_path转换为path对象
        import_file_path_obj = Path(import_file_path)

        if not import_file_path_obj.exists():
            raise FileProcessingError(message=f"文件{import_file_path_obj.name}不存在")

        # 3.判断文件类型
        suffix = import_file_path_obj.suffix.lower()
        state["is_pdf_read_enabled"] = False
        state["is_md_read_enabled"] = False
        if suffix == ".pdf":
            state["is_pdf_read_enabled"] = True
            state["pdf_path"] = import_file_path
        elif suffix == ".md":
            state["is_md_read_enabled"] = True
            state["md_path"] = import_file_path
        else:
            raise ValidationError(message=f"不支持的文件类型{import_file_path_obj.suffix}")

        # 4.获取文件名作为标题
        state["file_title"] = import_file_path_obj.stem

        return state


if __name__ == '__main__':
    setup_logging()
    logging.getLogger().info("请通过导入 API 传入旅游 PDF 或 Markdown 文件")
