import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODEL_JS = ROOT / "web" / "task_parts" / "41-unified-task-detail-model.js"
CONVERSATION_JS = ROOT / "web" / "task_parts" / "60-conversation.js"
PROJECT_MODES_JS = ROOT / "web" / "task_parts" / "77-project-modes.js"
PANEL_WIRE_JS = ROOT / "web" / "task_parts" / "79-panel-wire-upload.js"
TASK_JS = ROOT / "web" / "task.js"
OVERVIEW_JS = ROOT / "web" / "overview.js"
DETAIL_CSS = ROOT / "web" / "task_parts" / "42-unified-task-detail.css"
DRAWER_CSS = ROOT / "web" / "task_parts" / "61-conversation-task-tracking.css"


def extract_function(source: str, name: str) -> str:
    marker = f"function {name}("
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"未找到函数 {name}")
    paren_start = source.find("(", start)
    if paren_start < 0:
        raise AssertionError(f"函数 {name} 缺少参数列表")
    paren_depth = 0
    params_end = -1
    for index in range(paren_start, len(source)):
        char = source[index]
        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
            if paren_depth == 0:
                params_end = index
                break
    if params_end < 0:
        raise AssertionError(f"函数 {name} 参数列表未闭合")
    brace_start = source.find("{", params_end)
    if brace_start < 0:
        raise AssertionError(f"函数 {name} 缺少函数体")
    depth = 0
    for index in range(brace_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"函数 {name} 未闭合")


def run_node(script: str) -> None:
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Node 校验失败\nSTDOUT:\n"
            + result.stdout
            + "\nSTDERR:\n"
            + result.stderr
        )


class UnifiedTaskDetailUiLogicTests(unittest.TestCase):
    def test_model_maps_only_explicit_responsibility_slots(self) -> None:
        source = MODEL_JS.read_text(encoding="utf-8")
        script = f"""
function resolveTaskPrimaryStatusText(value) {{
  return String((value && value.task_primary_status) || value || "待办").trim();
}}
{source}
const model = normalizeUnifiedTaskDetailModel({{
  task_id: "task_1",
  task_title: "【进行中】【任务】统一任务详情",
  task_primary_status: "进行中",
  main_owner: {{ display_name: "前端-任务业务", channel_name: "子级04" }},
  collaborators: [{{ display_name: "产品-任务板块" }}],
  management_slot: [{{ display_name: "总控" }}],
  validators: [{{ display_name: "测试验收" }}],
  custom_roles: [
    {{ name: "用户审核位", members: [{{ display_name: "用户" }}] }},
  ],
}});
if (model.roles.main_owner.display_name !== "前端-任务业务") throw new Error("主负责位应来自 main_owner");
if (model.roles.executors[0].display_name !== "产品-任务板块") throw new Error("collaborators 应统一展示为执行位");
if (model.roles.management_slot[0].display_name !== "总控") throw new Error("管理位缺失");
if (model.roles.validators[0].display_name !== "测试验收") throw new Error("验证位缺失");
if (model.roles.user_reviewers[0].display_name !== "用户") throw new Error("用户审核位应来自显式 custom_roles");
"""
        run_node(script)

    def test_model_does_not_infer_roles_from_recent_action_text(self) -> None:
        source = MODEL_JS.read_text(encoding="utf-8")
        script = f"""
{source}
const model = normalizeUnifiedTaskDetailModel({{
  task_title: "【任务】没有责任位字段",
  latest_action_text: "主负责位应为某 Agent 的描述只存在于动作文本中",
  excerpt: "正文里写了验证位，但不能被当成结构化责任位",
}});
if (model.roles.hasData) throw new Error("禁止从最近动作或正文文本反推责任位");
if (!model.latestActionText) throw new Error("最近动作仍应进入互动区");
"""
        run_node(script)

    def test_conversation_detail_viewer_routes_to_unified_renderer(self) -> None:
        source = CONVERSATION_JS.read_text(encoding="utf-8")
        self.assertIn("openUnifiedTaskDetail(detail", source)
        self.assertIn("closeUnifiedTaskDetail({ notify: false })", source)

    def test_conversation_task_panel_is_list_only_and_uses_unified_cards(self) -> None:
        source = CONVERSATION_JS.read_text(encoding="utf-8")
        self.assertIn("buildUnifiedTaskListCard", source)
        self.assertIn("resolveConversationAgentOwnedTaskPayload", source)
        self.assertIn("conversationTaskMainOwnerMatchesSession", source)
        self.assertIn("当前 Agent 作为 main_owner", source)
        self.assertIn("当前主负责", source)
        self.assertIn("点击任务会打开中间统一详情弹框", source)
        self.assertIn("已完成主负责任务", source)
        drawer_source = (ROOT / "web" / "task_parts" / "76-runs-and-drawer.js").read_text(encoding="utf-8")
        self.assertIn("buildExplicitConversationSessionStub(STATE.project, STATE.channel, sid)", drawer_source)
        self.assertIn("STATE.selectedSessionExplicit", drawer_source)

    def test_detail_modal_and_task_drawer_visual_density_guardrails(self) -> None:
        detail_css = DETAIL_CSS.read_text(encoding="utf-8")
        drawer_css = DRAWER_CSS.read_text(encoding="utf-8")
        self.assertIn("font-size: clamp(18px, 2.4vw, 24px);", detail_css)
        self.assertIn(".mdview .unified-task-detail-title", detail_css)
        self.assertIn("box-shadow: 0 8px 22px rgba(15,23,42,0.04);", detail_css)
        self.assertIn("background: rgba(250,250,250,0.82);", detail_css)
        self.assertIn("height: min(900px, calc(100dvh - 28px));", detail_css)
        self.assertIn("display: flex;", detail_css)
        self.assertIn("flex-direction: column;", detail_css)
        self.assertIn(".bmodalb.unified-task-detail-modal-body", detail_css)
        self.assertIn("flex: 1 1 auto;", detail_css)
        self.assertIn("min-height: 0;", detail_css)
        self.assertIn("overflow-y: auto;", detail_css)
        self.assertIn("overflow-x: hidden;", detail_css)
        self.assertIn("overscroll-behavior: contain;", detail_css)
        self.assertIn("height: calc(100dvh - 16px);", detail_css)
        self.assertIn("width: min(560px, 96vw);", drawer_css)
        self.assertIn("top: var(--task-header-offset, 66px);", drawer_css)
        self.assertIn("top: var(--task-mobile-header-offset, 58px);", drawer_css)
        self.assertIn("z-index: 1320;", drawer_css)
        self.assertIn("gap: 8px;", drawer_css)

    def test_task_home_parent_child_cards_use_unified_modal_entry(self) -> None:
        source = PROJECT_MODES_JS.read_text(encoding="utf-8")
        self.assertIn("buildUnifiedTaskListCard", source)
        self.assertIn("buildUnifiedTaskChildGrid", source)
        self.assertIn("forceTaskType: \"parent\"", source)
        self.assertIn("forceTaskType: \"child\"", source)
        self.assertIn("openUnifiedDetail: true, forceTaskType: \"parent\"", source)
        self.assertIn("openUnifiedDetail: true, forceTaskType: \"child\"", source)
        self.assertNotIn("task-canvas-detail-open #detailView{\n          display:flex", source)

    def test_task_deeplink_ud_opens_unified_modal_once(self) -> None:
        panel_source = PANEL_WIRE_JS.read_text(encoding="utf-8")
        task_source = TASK_JS.read_text(encoding="utf-8")
        self.assertIn("const ud = params.get(\"ud\")", panel_source)
        self.assertIn("STATE.unifiedDetailRequested = ud === \"1\" || ud === \"true\"", panel_source)
        self.assertIn("if (tid === null) STATE.selectedTaskId = \"\"", panel_source)
        self.assertIn("openUnifiedTaskDetailForSelection(selected, { source: \"task-deeplink\" })", panel_source)
        self.assertIn("function openUnifiedTaskDetailForSelection", task_source)
        self.assertIn("openUnifiedTaskDetail(item", task_source)
        self.assertIn("function taskDetailForceTypeForSelection", task_source)
        self.assertIn("return \"parent\"", task_source)
        self.assertIn("return \"child\"", task_source)
        self.assertIn("forceTaskType: taskDetailForceTypeForSelection(item, opts)", task_source)

    def test_overview_task_url_can_deeplink_to_unified_task_detail(self) -> None:
        source = OVERVIEW_JS.read_text(encoding="utf-8")
        to_task_url = extract_function(source, "toTaskUrl")
        script = f"""
const taskBase = "/share/project-task-dashboard.html";
{to_task_url}
const url = toTaskUrl("task_dashboard", "子级04", {{
  panelMode: "t",
  taskPath: "任务规划/子级04/任务/【任务】demo.md",
  taskId: "task_demo",
  unifiedDetail: true,
}});
if (!url.includes("pm=t")) throw new Error("overview 任务节点应进入任务面板");
if (!url.includes("sp=")) throw new Error("overview 任务节点应携带任务路径");
if (!url.includes("tid=task_demo")) throw new Error("overview 任务节点应携带任务 id");
if (!url.includes("ud=1")) throw new Error("overview 任务节点应标识统一详情入口");
"""
        run_node(script)


if __name__ == "__main__":
    unittest.main()
