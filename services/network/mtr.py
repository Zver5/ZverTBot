import asyncio
import re

from utils.logger import logger

# =========================
# CONFIG
# =========================

MTR_TIMEOUT = 25
MAX_HOPS = 15
PACKETS = 10


# =========================
# RUN MTR
# =========================


async def run_mtr(target: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "mtr",
            "-n",
            "-r",  # report mode
            "-c",
            str(PACKETS),
            "-m",
            str(MAX_HOPS),
            target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=MTR_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return "❌ MTR timeout"

        err = stderr.decode(errors="ignore").strip()
        if err:
            return f"❌ mtr error: {err}"

        return stdout.decode(errors="ignore")

    except Exception as e:
        return f"❌ system error: {e}"


# =========================
# PARSER (100% robust)
# =========================

IP_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)")
LOSS_RE = re.compile(r"(\d+\.?\d*)%")
FLOAT_RE = re.compile(r"(\d+\.\d+)")


def parse_mtr(output: str):
    data = []

    for line in output.splitlines():
        line = line.strip()

        if not line or "Loss%" in line:
            continue

        # hop
        hop_match = re.match(r"^(\d+)\.", line)
        if not hop_match:
            continue

        hop = hop_match.group(1)

        # ip
        ip_match = IP_RE.search(line)
        if not ip_match:
            continue
        ip = ip_match.group(1)

        # Разбираем числовые колонки MTR по их позиции,
        # не включая числа из IP-адреса.
        parts = line.split()

        try:
            ip_index = parts.index(ip)
        except ValueError:
            continue

        loss_match = LOSS_RE.search(line)
        loss = float(loss_match.group(1)) if loss_match else 0.0

        if loss_match:
            try:
                loss_index = next(
                    i for i, part in enumerate(parts) if part.endswith("%")
                )
                avg = float(parts[loss_index + 3])
            except (StopIteration, IndexError, ValueError):
                avg = 0.0
        else:
            try:
                avg = float(parts[ip_index + 3])
            except (IndexError, ValueError):
                avg = 0.0

        data.append({"hop": hop, "ip": ip, "loss": loss, "avg": avg})

    return data


# =========================
# ANALYTICS
# =========================


def analyze(data):
    if not data:
        return "❌ Нет данных"

    for r in data:
        if r["loss"] >= 20:
            return f"🚨 Потери на хопе {r['hop']} ({r['ip']})"

    if max(r["avg"] for r in data) > 150:
        return "⚠️ Высокая задержка"

    return "✅ Маршрут стабилен"


# =========================
# FORMAT
# =========================


def format_mtr(data, target: str) -> str:
    if not data:
        return "❌ Нет данных"

    status = analyze(data)

    lines = [
        "📡 <b>MTR диагностика</b>",
        f"🎯 <code>{target}</code>",
        "",
        status,
        "",
        "Hop | IP | Loss | Avg",
        "----|----|------|------",
    ]

    for r in data:
        icon = "🟢" if r["loss"] < 1 else "🟡" if r["loss"] < 5 else "🔴"

        lines.append(
            f"{r['hop']} | {r['ip']} | {icon} {r['loss']:.1f}% | {r['avg']:.1f}"
        )

    return "<pre>" + "\n".join(lines) + "</pre>"


# =========================
# MAIN
# =========================


async def diagnose(target: str) -> str:
    raw = await run_mtr(target)

    if raw.startswith("❌"):
        return raw

    parsed = parse_mtr(raw)
    return format_mtr(parsed, target)


# =========================
# TEST
# =========================

if __name__ == "__main__":

    async def main():
        result = await diagnose("8.8.8.8")
        logger.debug(
            "mtr.diagnose.completed | target=%s | result=%s",
            "8.8.8.8",
            result,
        )

    asyncio.run(main())
