"""旧商品节点的兼容别名。旅游版统一使用 NodeTravelQueryPrepare。"""

from processor.query_processor.nodes.node_travel_query_prepare import NodeTravelQueryPrepare


class NodeItemNameConfirm(NodeTravelQueryPrepare):
    """兼容旧导入路径，避免外部脚本导入失败。"""

    name = "node_travel_query_prepare"
