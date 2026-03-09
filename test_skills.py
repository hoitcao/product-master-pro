#!/usr/bin/env python3
"""
产品大师 Pro —— Skill 自动化测试脚本

功能：
1. 自动读取 skill-*.md 文件拼装 system prompt
2. 向 Anthropic Claude API 发送 7 个测试用例（每个 skill 一个）
3. 保存 AI 原始输出到 test_results/ 目录
4. 自动检查输出格式是否符合每个 skill 的输出模板
5. 生成汇总测试报告

使用方法：
  1. 安装依赖：pip install -r requirements.txt
  2. 设置环境变量：export ANTHROPIC_API_KEY="your-key-here"
     或复制 .env.example 为 .env 并填入 key
  3. 运行：python test_skills.py
  4. 可选参数：
     --skills 1 3 6        只测试指定 skill（编号 1-7）
     --model claude-sonnet-4-20250514  指定模型
     --max-tokens 8192     指定最大 token 数
     --output-dir results  指定输出目录
"""

import os
import re
import sys
import json
import glob
import time
import argparse
from pathlib import Path
from datetime import datetime

try:
    import anthropic
except ImportError:
    print("错误：请先安装 anthropic 库")
    print("  pip install anthropic")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv 是可选的


# ============================================================
# 配置
# ============================================================

SCRIPT_DIR = Path(__file__).parent.resolve()

SKILL_FILES = {
    1: "skill-1-定义需求.md",
    2: "skill-2-理解用户.md",
    3: "skill-3-做不做.md",
    4: "skill-4-竞争分析.md",
    5: "skill-5-执行策略.md",
    6: "skill-6-传播策略.md",
    7: "skill-7-产品圆桌.md",
}

SKILL_NAMES = {
    1: "定义需求",
    2: "理解用户",
    3: "做不做",
    4: "竞争分析",
    5: "执行策略",
    6: "传播策略",
    7: "产品圆桌",
}


# ============================================================
# 测试用例
# ============================================================

TEST_CASES = {
    1: {
        "name": "定义需求",
        "input": (
            "定义需求：我想做一个帮自由职业者管理收入和税务的工具。"
            "现在他们都是用 Excel 或者手动记账，很多人到年底才发现自己欠了一大笔税。"
            "我觉得这个市场很大。"
        ),
        "description": "测试能否把开放式愿望转为封闭目标、识别JTBD、判定需求类型",
    },
    2: {
        "name": "理解用户",
        "input": (
            "理解用户：我们做了一个线上买菜App，发现一个奇怪的现象——"
            "很多50多岁的阿姨，每天早上6点半准时打开App浏览，但80%的人浏览了10分钟后没有下单，"
            "而是关掉App去了楼下菜市场。但她们第二天还是会打开App。"
            "我们不理解她们到底在干什么。"
        ),
        "description": "测试能否还原场景故事、关注沉默信号、识别用户真实待办任务",
    },
    3: {
        "name": "做不做",
        "input": (
            "做不做：我想做一个面向中小学老师的AI批改作文工具。"
            "老师每天要批改几十篇作文，很痛苦。"
            "我打算用大模型做自动批改+批注。"
            "团队3个人（1个产品+2个开发），启动资金20万，"
            "打算先做成微信小程序。"
        ),
        "description": "测试马氏三问、俞军公式打分、商业账、做/改/算了判定",
    },
    4: {
        "name": "竞争分析",
        "input": (
            "竞争分析：我们是一家做企业级即时通讯的创业公司，"
            "产品类似飞书/钉钉但专注于金融行业合规场景"
            "（消息留痕、审计、数据不出域）。"
            "目前有3家银行在用我们的产品。"
            "想搞清楚我们的竞争优势在哪，"
            "以及钉钉和飞书如果也做金融合规版本，我们还能不能活。"
        ),
        "description": "测试护城河三重测试、博弈分析、特许经营区边界、价值评估",
    },
    5: {
        "name": "执行策略",
        "input": (
            "执行策略：我们确定要做一个"宠物健康助手"App。"
            "计划的功能包括：AI看诊（拍照识别宠物皮肤病）、疫苗提醒、"
            "附近宠物医院推荐、宠物社区、宠物食品商城、宠物保险比价、遛狗打卡。"
            "团队4个人，想3个月内上线MVP。"
        ),
        "description": "测试能否果断砍功能、找到那个'1'、设计预型测试、给出行动计划",
    },
    6: {
        "name": "传播策略",
        "input": (
            "传播策略：我们的产品叫"速记侠"，是一个AI会议纪要工具，"
            "能自动把会议录音变成结构化的纪要，标注待办事项和负责人。"
            "目前主要面向互联网公司的中层管理者。"
        ),
        "description": "测试战略推演、四大算法生成文案、邻居测试+100年测试、口语化",
    },
    7: {
        "name": "产品圆桌",
        "input": (
            "产品圆桌：我想做一个针对独居年轻人的"一人食"预制菜品牌。"
            "现在的预制菜要么是大分量家庭装，要么味道很差。"
            "我想做小份量、口味好、5分钟出锅的预制菜，"
            "主打"一个人也要好好吃饭"。"
        ),
        "description": "测试全流程串联①→⑥、上下文传递、矛盾检测、大师辩论",
    },
}


# ============================================================
# 格式检查规则
# ============================================================

FORMAT_CHECKS = {
    1: {
        "name": "定义需求",
        "required_sections": [
            "定义需求",
            "状态 vs 目标",
            "封闭目标",
            "待办任务",
            "需求类型",
            "存在感公式",
        ],
        "required_patterns": [
            (r"给谁用", "封闭目标表格中应包含'给谁用'"),
            (r"解决什么", "封闭目标表格中应包含'解决什么'"),
            (r"怎么算成功", "封闭目标表格中应包含'怎么算成功'"),
            (r"你有什么", "封闭目标表格中应包含'你有什么'"),
            (r"大雇用", "应区分大雇用和小雇用"),
            (r"小雇用", "应区分大雇用和小雇用"),
            (r"(痛点|爽点|痒点)", "应判定需求类型（痛点/爽点/痒点）"),
            (r"我是.*通过.*证明", "应包含存在感公式"),
            (r"下一步", "应有下一步建议"),
        ],
    },
    2: {
        "name": "理解用户",
        "required_sections": [
            "理解用户",
            "场景故事",
            "用户画像",
            "心理动力",
            "本质洞察",
        ],
        "required_patterns": [
            (r"小雇用", "应识别'小雇用'时刻"),
            (r"待办任务|JTBD", "应包含待办任务/JTBD分析"),
            (r"沉默信号|不消费|权宜之计", "应关注沉默信号"),
            (r"典型人物|👤", "应输出典型人物速写"),
            (r"口头禅", "典型人物应有口头禅"),
            (r"(大明|笨笨|小闲)", "应判定用户类型"),
            (r"推力|拉力|惯性|焦虑", "应做力场分析"),
            (r"(愉悦|爽|不爽|愤怒|恐惧)", "应有情绪刻度分析"),
            (r"谁不是", "应有反面画像"),
            (r"下一步", "应有下一步建议"),
        ],
    },
    3: {
        "name": "做不做",
        "required_sections": [
            "做不做",
            "马氏三问",
            "用户价值公式",
            "商业账",
            "最终判定",
        ],
        "required_patterns": [
            (r"擅长", "马氏三问应包含'擅长'维度"),
            (r"(不做|不用).*损失", "马氏三问应评估不做的损失"),
            (r"竞争优势", "马氏三问应评估竞争优势"),
            (r"新体验.*\d", "用户价值公式应有新体验打分"),
            (r"旧体验.*\d", "用户价值公式应有旧体验打分（不能为0）"),
            (r"替换成本", "应有替换成本分析"),
            (r"认知成本|信任成本|迁移成本|金钱成本|时间成本", "替换成本应有五维拆解"),
            (r"(流量|转化率|客单价)", "商业账应有流量变现公式"),
            (r"(🟢.*做|🟡.*改|🔴.*算了|做.*值得|改一改|算了|别做)", "应有明确的做/改/算了判定"),
            (r"下一步", "应有下一步建议"),
        ],
    },
    4: {
        "name": "竞争分析",
        "required_sections": [
            "竞争分析",
            "竞争领域",
            "破局点",
            "护城河",
        ],
        "required_patterns": [
            (r"地理范围|地理", "应界定地理范围"),
            (r"(边缘|锋利|自增长)", "应检查破局点三要素"),
            (r"供给", "护城河应测试供给侧优势"),
            (r"需求.*锁定|转换成本|习惯", "护城河应测试需求侧优势"),
            (r"规模", "护城河应测试规模经济优势"),
            (r"(路径A|路径B|无护城河|有护城河|无壁垒|有壁垒)", "应有路径判定"),
            (r"(博弈|对手|反击|容纳)", "应有博弈分析或说明为何跳过"),
            (r"(EPV|盈利能力|资产.*价值)", "应有价值评估"),
            (r"下一步", "应有下一步建议"),
        ],
    },
    5: {
        "name": "执行策略",
        "required_sections": [
            "执行策略",
            "核心功能",
            "砍掉",
        ],
        "required_patterns": [
            (r"(那个.*1|全力做|核心功能)", "应找到那个'1'"),
            (r"砍|去掉|降级|不做", "应有砍功能列表"),
            (r"极简规则|一句话|核心规则", "应提取极简规则"),
            (r"(3秒|小白|说明书|地铁)", "应做小白压力测试"),
            (r"超能力|成就感", "应定义用户超能力"),
            (r"(XYZ|假说|预型|假门|土耳其人|一人公司)", "应设计预型测试"),
            (r"(Day|第.*天|行动计划|一周)", "应有行动计划"),
            (r"(北极星|指标|盯.*数)", "应有北极星指标"),
            (r"下一步", "应有下一步建议"),
        ],
    },
    6: {
        "name": "传播策略",
        "required_sections": [
            "传播策略",
            "战略洞察",
            "品牌谚语|推荐",
            "避坑",
        ],
        "required_patterns": [
            (r"(卖的不是|顾客买的是)", "战略洞察应区分表面产品和真实需求"),
            (r"(真正的对手|竞争参照)", "应识别真正的竞争对手"),
            (r"购买理由", "应提取核心购买理由"),
            (r"(1️⃣|2️⃣|3️⃣|第一条|第二条|第三条)", "应输出至少3条候选文案"),
            (r"(填空|指令|顺口溜|押韵|承诺|场景寄生)", "应标注文案使用的算法类型"),
            (r"转述场景|顾客.*说", "每条文案应有转述场景"),
            (r"(千万别说|避坑|不要说)", "应有避坑提示"),
            (r"速记侠", "文案中应出现品牌名（品牌资产不流失）"),
        ],
    },
    7: {
        "name": "产品圆桌",
        "required_sections": [
            "产品圆桌|诊断书",
            "定义需求",
            "理解用户",
            "做不做",
        ],
        "required_patterns": [
            (r"封闭目标|谁.*什么.*多少", "阶段①应有封闭目标"),
            (r"(用户画像|典型人物)", "阶段②应有用户画像"),
            (r"(用户价值|马氏三问)", "阶段③应有价值计算"),
            (r"(🟢|🟡|🔴|做.*值得|改一改|算了)", "阶段③应有判定"),
            (r"(傅盛|俞军|张小龙|周鸿祎|曹政|Kathy)", "应有大师辩论"),
            (r"(最终判定|一句话结论)", "应有最终判定"),
        ],
    },
}


# ============================================================
# 工具函数
# ============================================================

def load_skill_files() -> str:
    """读取所有 skill markdown 文件，拼装为 system prompt"""
    parts = []
    parts.append("你是「产品大师 Pro」，一个产品分析 AI 助手。你拥有以下 7 个 Skill，根据用户输入的触发词激活对应 Skill 并严格按其工作流和输出格式执行。\n")
    parts.append("=" * 60)

    for idx in sorted(SKILL_FILES.keys()):
        filepath = SCRIPT_DIR / SKILL_FILES[idx]
        if not filepath.exists():
            print(f"  ⚠️  文件不存在: {filepath}")
            continue
        content = filepath.read_text(encoding="utf-8")
        parts.append(f"\n{'=' * 60}")
        parts.append(f"## Skill {idx}: {SKILL_NAMES[idx]}")
        parts.append("=" * 60)
        parts.append(content)

    return "\n".join(parts)


def check_format(skill_id: int, output: str) -> dict:
    """检查输出是否符合格式模板，返回检查结果"""
    checks = FORMAT_CHECKS.get(skill_id)
    if not checks:
        return {"passed": True, "total": 0, "failures": [], "warnings": []}

    results = {
        "skill_name": checks["name"],
        "total_section_checks": len(checks["required_sections"]),
        "total_pattern_checks": len(checks["required_patterns"]),
        "section_results": [],
        "pattern_results": [],
        "failures": [],
        "warnings": [],
    }

    # 检查必需的章节标题
    for section in checks["required_sections"]:
        found = bool(re.search(section, output, re.IGNORECASE))
        results["section_results"].append({
            "section": section,
            "found": found,
        })
        if not found:
            results["failures"].append(f"缺少章节: {section}")

    # 检查必需的内容模式
    for pattern, description in checks["required_patterns"]:
        found = bool(re.search(pattern, output, re.IGNORECASE))
        results["pattern_results"].append({
            "pattern": pattern,
            "description": description,
            "found": found,
        })
        if not found:
            results["warnings"].append(f"未检测到: {description}")

    total = results["total_section_checks"] + results["total_pattern_checks"]
    passed_sections = sum(1 for r in results["section_results"] if r["found"])
    passed_patterns = sum(1 for r in results["pattern_results"] if r["found"])
    passed = passed_sections + passed_patterns

    results["total"] = total
    results["passed"] = passed
    results["score"] = round(passed / total * 100, 1) if total > 0 else 100
    results["all_passed"] = len(results["failures"]) == 0 and len(results["warnings"]) == 0

    return results


def format_check_report(results: dict) -> str:
    """格式化单个 skill 的检查报告"""
    lines = []
    lines.append(f"  格式得分: {results['score']}% ({results['passed']}/{results['total']})")

    if results["failures"]:
        lines.append(f"  ❌ 失败 ({len(results['failures'])}):")
        for f in results["failures"]:
            lines.append(f"     • {f}")

    if results["warnings"]:
        lines.append(f"  ⚠️  警告 ({len(results['warnings'])}):")
        for w in results["warnings"]:
            lines.append(f"     • {w}")

    if results["all_passed"]:
        lines.append("  ✅ 所有格式检查通过!")

    return "\n".join(lines)


# ============================================================
# 主逻辑
# ============================================================

def run_test(
    client: anthropic.Anthropic,
    system_prompt: str,
    skill_id: int,
    model: str,
    max_tokens: int,
) -> dict:
    """运行单个测试用例"""
    test_case = TEST_CASES[skill_id]
    print(f"\n{'─' * 60}")
    print(f"🧪 测试 Skill {skill_id}: {test_case['name']}")
    print(f"   输入: {test_case['input'][:80]}...")
    print(f"   目的: {test_case['description']}")
    print(f"   模型: {model}")
    print(f"   等待响应中...")

    start_time = time.time()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": test_case["input"]}
            ],
        )

        elapsed = time.time() - start_time
        output_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                output_text += block.text

        # 统计 token
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        print(f"   ✅ 响应完成 ({elapsed:.1f}s, 输入 {input_tokens} tokens, 输出 {output_tokens} tokens)")
        print(f"   输出长度: {len(output_text)} 字符")

        # 格式检查
        check_results = check_format(skill_id, output_text)
        print(format_check_report(check_results))

        return {
            "skill_id": skill_id,
            "skill_name": test_case["name"],
            "input": test_case["input"],
            "output": output_text,
            "elapsed_seconds": round(elapsed, 1),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": model,
            "format_check": check_results,
            "error": None,
        }

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"   ❌ 错误: {e}")
        return {
            "skill_id": skill_id,
            "skill_name": test_case["name"],
            "input": test_case["input"],
            "output": None,
            "elapsed_seconds": round(elapsed, 1),
            "input_tokens": 0,
            "output_tokens": 0,
            "model": model,
            "format_check": None,
            "error": str(e),
        }


def save_results(results: list, output_dir: Path):
    """保存测试结果到文件"""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 保存每个 skill 的原始输出
    for r in results:
        if r["output"]:
            filename = f"skill-{r['skill_id']}-{r['skill_name']}.md"
            filepath = output_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# Skill {r['skill_id']}: {r['skill_name']} — 测试输出\n\n")
                f.write(f"> 模型: {r['model']}  \n")
                f.write(f"> 时间: {timestamp}  \n")
                f.write(f"> 耗时: {r['elapsed_seconds']}s  \n")
                f.write(f"> Token: 输入 {r['input_tokens']}, 输出 {r['output_tokens']}  \n\n")
                f.write(f"## 输入\n\n{r['input']}\n\n")
                f.write(f"## 输出\n\n{r['output']}\n")
            print(f"  💾 已保存: {filepath}")

    # 保存汇总报告
    report_path = output_dir / f"report_{timestamp}.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("产品大师 Pro —— Skill 自动化测试报告\n")
        f.write(f"时间: {timestamp}\n")
        f.write("=" * 70 + "\n\n")

        total_tests = len(results)
        success_tests = sum(1 for r in results if r["error"] is None)
        total_tokens_in = sum(r["input_tokens"] for r in results)
        total_tokens_out = sum(r["output_tokens"] for r in results)
        total_time = sum(r["elapsed_seconds"] for r in results)

        f.write(f"测试总数: {total_tests}\n")
        f.write(f"成功: {success_tests}  失败: {total_tests - success_tests}\n")
        f.write(f"总耗时: {total_time:.1f}s\n")
        f.write(f"总 Token: 输入 {total_tokens_in}, 输出 {total_tokens_out}\n\n")

        f.write("-" * 70 + "\n")
        f.write(f"{'Skill':<20} {'状态':<8} {'耗时':<10} {'格式得分':<12} {'问题数':<8}\n")
        f.write("-" * 70 + "\n")

        for r in results:
            status = "✅ 成功" if r["error"] is None else "❌ 失败"
            elapsed = f"{r['elapsed_seconds']}s"
            if r["format_check"]:
                score = f"{r['format_check']['score']}%"
                issues = len(r["format_check"]["failures"]) + len(r["format_check"]["warnings"])
            else:
                score = "N/A"
                issues = "-"
            f.write(f"Skill {r['skill_id']}: {r['skill_name']:<12} {status:<8} {elapsed:<10} {score:<12} {issues}\n")

        f.write("-" * 70 + "\n\n")

        # 详细格式检查
        f.write("\n" + "=" * 70 + "\n")
        f.write("详细格式检查结果\n")
        f.write("=" * 70 + "\n\n")

        for r in results:
            f.write(f"\n--- Skill {r['skill_id']}: {r['skill_name']} ---\n")
            if r["error"]:
                f.write(f"  错误: {r['error']}\n")
                continue
            if r["format_check"]:
                fc = r["format_check"]
                f.write(f"  格式得分: {fc['score']}%\n")
                if fc["failures"]:
                    f.write(f"  ❌ 失败:\n")
                    for fail in fc["failures"]:
                        f.write(f"     • {fail}\n")
                if fc["warnings"]:
                    f.write(f"  ⚠️  警告:\n")
                    for warn in fc["warnings"]:
                        f.write(f"     • {warn}\n")
                if fc["all_passed"]:
                    f.write(f"  ✅ 全部通过\n")

    print(f"\n  📋 测试报告: {report_path}")

    # 保存 JSON 原始数据（方便程序化处理）
    json_path = output_dir / f"raw_{timestamp}.json"
    json_results = []
    for r in results:
        jr = dict(r)
        # output 太长，在 JSON 里只保留前 500 字
        if jr["output"] and len(jr["output"]) > 500:
            jr["output_preview"] = jr["output"][:500] + "..."
            jr["output_full_length"] = len(jr["output"])
        del jr["output"]
        json_results.append(jr)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_results, f, ensure_ascii=False, indent=2)
    print(f"  📊 原始数据: {json_path}")


def print_summary(results: list):
    """打印最终汇总"""
    print("\n" + "=" * 60)
    print("📊 测试汇总")
    print("=" * 60)

    total = len(results)
    success = sum(1 for r in results if r["error"] is None)
    print(f"\n  总计: {total} 个 Skill 测试")
    print(f"  成功: {success}  失败: {total - success}")

    total_time = sum(r["elapsed_seconds"] for r in results)
    total_in = sum(r["input_tokens"] for r in results)
    total_out = sum(r["output_tokens"] for r in results)
    print(f"  总耗时: {total_time:.1f}s")
    print(f"  总 Token: 输入 {total_in}, 输出 {total_out}")

    print(f"\n  {'Skill':<25} {'状态':<10} {'格式得分':<12}")
    print(f"  {'─' * 47}")
    for r in results:
        name = f"Skill {r['skill_id']}: {r['skill_name']}"
        status = "✅" if r["error"] is None else "❌"
        score = f"{r['format_check']['score']}%" if r["format_check"] else "N/A"
        print(f"  {name:<25} {status:<10} {score}")

    # 总体格式得分
    scores = [r["format_check"]["score"] for r in results if r["format_check"]]
    if scores:
        avg_score = sum(scores) / len(scores)
        print(f"\n  📈 平均格式得分: {avg_score:.1f}%")
        if avg_score >= 90:
            print("  🎉 格式质量优秀!")
        elif avg_score >= 70:
            print("  👍 格式质量良好，有改进空间")
        else:
            print("  ⚠️  格式质量需要改进")


def main():
    parser = argparse.ArgumentParser(description="产品大师 Pro Skill 自动化测试")
    parser.add_argument(
        "--skills",
        nargs="+",
        type=int,
        default=None,
        help="指定要测试的 Skill 编号（1-7），默认全部测试。示例: --skills 1 3 6",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="Anthropic 模型名称，默认 claude-sonnet-4-20250514",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
        help="每次请求的最大输出 token 数，默认 8192",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="test_results",
        help="输出目录，默认 test_results",
    )

    args = parser.parse_args()

    # 确定测试范围
    skill_ids = args.skills if args.skills else sorted(TEST_CASES.keys())
    for sid in skill_ids:
        if sid not in TEST_CASES:
            print(f"❌ 无效的 Skill 编号: {sid}（有效范围: 1-7）")
            sys.exit(1)

    # 检查 API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ 未设置 ANTHROPIC_API_KEY 环境变量")
        print("   请执行: export ANTHROPIC_API_KEY='your-key-here'")
        print("   或将 .env.example 复制为 .env 并填入 key")
        sys.exit(1)

    print("=" * 60)
    print("🧠 产品大师 Pro —— Skill 自动化测试")
    print("=" * 60)
    print(f"  模型: {args.model}")
    print(f"  最大 Token: {args.max_tokens}")
    print(f"  测试 Skill: {skill_ids}")
    print(f"  输出目录: {args.output_dir}")

    # 加载 skill 文件拼装 system prompt
    print(f"\n📄 加载 Skill 文件...")
    system_prompt = load_skill_files()
    print(f"  System prompt 长度: {len(system_prompt)} 字符")

    # 初始化客户端
    client = anthropic.Anthropic(api_key=api_key)

    # 运行测试
    output_dir = SCRIPT_DIR / args.output_dir
    results = []

    for skill_id in skill_ids:
        result = run_test(client, system_prompt, skill_id, args.model, args.max_tokens)
        results.append(result)
        # 简单限流：每次请求间隔 2 秒
        if skill_id != skill_ids[-1]:
            time.sleep(2)

    # 保存结果
    print(f"\n💾 保存结果到 {output_dir}/")
    save_results(results, output_dir)

    # 打印汇总
    print_summary(results)

    print("\n✅ 测试完成!")


if __name__ == "__main__":
    main()
