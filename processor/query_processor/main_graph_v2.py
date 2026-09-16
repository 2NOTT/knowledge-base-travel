"""旅游查询工作流兼容入口。"""

from processor.query_processor.main_graph import KBQueryWorkflow


class KBQueryWorkflowV2(KBQueryWorkflow):
    """保留旧导入路径，实际使用统一的旅游查询图。"""


if __name__ == "__main__":
    print(KBQueryWorkflowV2().compile().get_graph().draw_ascii())
