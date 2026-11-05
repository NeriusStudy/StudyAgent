# packages/core/src/agentcore/tools/registry.py
from agentschema import ToolHandler, ToolDefinition


class ToolRegistry:
    """
    工具注册表：只负责"登记"和"查找"，不执行任何工具。

    职责边界：
    - 登记工具（register），重复注册立刻报错（早失败）
    - 按名字取出工具（get），未知工具立刻报错
    - 生成给模型看的工具列表（list_definitions），转成 schema 里的 ToolDefinition

    不负责：
    - 工具执行（在 executor.py）
    - 具体工具实现（在 builtin/ 或用户自己的包里）
    - 参数校验（由工具自己的 execute 内部完成）
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolHandler] = {}

    def register(self, tool: ToolHandler) -> None:
        """登记一个工具。重名立刻报错，避免静默覆盖。"""
        if tool.name in self._tools:
            raise ValueError(f"工具已注册: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolHandler:
        """按名字取工具。未知工具明确抛 KeyError，不返回 None。"""
        if name not in self._tools:
            raise KeyError(f"未知工具: {name}")
        return self._tools[name]

    def list_definitions(self) -> list[ToolDefinition]:
        """生成给模型看的工具清单（转为 schema 中的 ToolDefinition）。"""
        return [
            ToolDefinition(
                name=t.name,
                description=t.description,
                parameters=t.parameters,
            )
            for t in self._tools.values()
        ]

    def __contains__(self, name: str) -> bool:
        """支持 `'calculator' in registry` 这种写法。"""
        return name in self._tools

    def __len__(self) -> int:
        """支持 `len(registry)`，方便统计和日志。"""
        return len(self._tools)