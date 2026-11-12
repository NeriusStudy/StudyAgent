# packages/core/src/agentcore/tools/registry.py
import importlib
from agentschema import ToolHandler, ToolDefinition


class ToolRegistry:
    """
    工具注册表：只负责“登记”和“查找”，不执行任何工具。

    职责边界：
    - 登记工具（register），重复注册立刻报错
    - 按名字取出工具（get），未知工具立刻报错
    - 生成给模型看的工具列表（list_definitions）
    - 按配置懒加载本地工具（register_local_tool）

    不负责：
    - 工具执行（在 executor.py）
    - 具体工具实现（在 builtin/ 或用户自己的包里）
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolHandler] = {}

    def register(self, tool: ToolHandler) -> None:
        """登记一个工具。重名立刻报错，避免静默覆盖。"""
        if tool.name in self._tools:
            raise ValueError(f"工具已注册：{tool.name}")
        self._tools[tool.name] = tool

    def register_local_tool(self, name: str) -> None:
        """
        按名称懒加载本地 builtin 工具并注册。

        约定：agentcore/tools/builtin/<name>.py 中必须有一个类，
        类名由模块名首字母大写 + 其余部分 + 'Tool' 组成。
        例如 name='calculator' -> CalculatorTool
        """
        module_name = f"agentcore.tools.builtin.{name}"
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            raise ValueError(f"无法加载本地工具 {name}: {e}") from e

        # 推断类名：calculator -> CalculatorTool
        class_name = "".join(part.capitalize() for part in name.split("_")) + "Tool"
        if not hasattr(module, class_name):
            raise ValueError(f"模块 {module_name} 中未找到类 {class_name}")

        tool_cls = getattr(module, class_name)
        self.register(tool_cls())

    def get(self, name: str) -> ToolHandler:
        """按名字取工具。未知工具明确抛 KeyError。"""
        if name not in self._tools:
            raise KeyError(f"未知工具：{name}")
        return self._tools[name]

    def list_definitions(self) -> list[ToolDefinition]:
        """生成给模型看的工具清单。"""
        return [
            ToolDefinition(
                name=t.name,
                description=t.description,
                parameters=t.parameters,
            )
            for t in self._tools.values()
        ]

    def clear(self) -> None:
        """清空所有已注册工具（仅用于热重载场景）。"""
        self._tools.clear()

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)