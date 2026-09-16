import logging
from typing import Dict

from processor.import_processor.base import BaseNode, setup_logging
from processor.import_processor.exceptions import ImportProcessError
from processor.import_processor.state import ImportGraphState


class TestNode(BaseNode):
    name="node_test"

    def process(self,state: Dict) -> Dict:

        # self.logger.info(f"--- {self.name} ---正在执行")
        self.log_step("MCP查询","开始执行")
        return {}

if __name__ == "__main__":
    #激活体质
    setup_logging(logging.INFO)


    test_node=TestNode()

    #使用对象()的方式相当于调用了对象__call__()  就是调用了base里的process方法
    test_node({"abc":123})