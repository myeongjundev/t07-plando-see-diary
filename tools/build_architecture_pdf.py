# -*- coding: utf-8 -*-
"""제출용 아키텍처 브리프(가로 A4 8쪽)를 그린다.

    python tools/build_architecture_pdf.py

    출력: output/pdf/T07-security-network-architecture.pdf

이 파일이 tmp/가 아니라 tools/에 있는 이유: docs/STATUS.md와 제출 체크리스트가 저
PDF를 제출물로 지목한다. 제출물을 만든 코드가 gitignore 아래 있으면, 그 폴더를 비우는
순간 제출물을 다시 만들 수 없다.

필요한 것
  - reportlab
  - 맑은 고딕(malgun.ttf / malgunbd.ttf). 한글을 그리는 문서라 대체 글꼴로 바꾸면
    줄바꿈 위치가 달라져 글자가 상자 밖으로 넘친다. 그래서 없으면 조용히 넘어가지
    않고 멈춘다 — Windows 기본 글꼴이고, 다른 OS에서는 MALGUN_DIR로 폴더를 준다.
"""
import os
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "T07-security-network-architecture.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

FONT_DIR = Path(os.environ.get("MALGUN_DIR", r"C:\Windows\Fonts"))
_regular, _bold = FONT_DIR / "malgun.ttf", FONT_DIR / "malgunbd.ttf"
_missing = [str(p) for p in (_regular, _bold) if not p.is_file()]
if _missing:
    raise SystemExit(
        "맑은 고딕을 찾지 못했습니다: " + ", ".join(_missing)
        + "\nMALGUN_DIR 환경변수로 글꼴 폴더를 지정하세요."
    )
pdfmetrics.registerFont(TTFont("Malgun", str(_regular)))
pdfmetrics.registerFont(TTFont("Malgun-Bold", str(_bold)))

W, H = landscape(A4)
NAVY = HexColor("#0B1220")
INK = HexColor("#172033")
MUTED = HexColor("#667085")
BLUE = HexColor("#2563EB")
PALE = HexColor("#EFF6FF")
PAPER = HexColor("#F8FAFC")
WHITE = HexColor("#FFFFFF")
LINE = HexColor("#D8E1EE")
GREEN = HexColor("#16A34A")
RED = HexColor("#DC2626")
AMBER = HexColor("#D97706")

c = canvas.Canvas(str(OUT), pagesize=(W, H))


def para(text, x, y_top, width, height, size=10, color=INK, bold=False, leading=None):
    style = ParagraphStyle(
        name="p",
        fontName="Malgun-Bold" if bold else "Malgun",
        fontSize=size,
        leading=leading or size * 1.45,
        textColor=color,
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    p = Paragraph(text, style)
    p.wrapOn(c, width, height)
    p.drawOn(c, x, y_top - height)


def rect(x, y, w, h, fill=WHITE, stroke=LINE, radius=4):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(0.7)
    c.roundRect(x, y, w, h, radius, fill=1, stroke=1)


def header(kicker, title, page):
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(BLUE)
    c.setFont("Malgun-Bold", 9)
    c.drawString(18 * mm, H - 16 * mm, kicker)
    c.setFillColor(INK)
    c.setFont("Malgun-Bold", 24)
    c.drawString(18 * mm, H - 30 * mm, title)
    c.setStrokeColor(LINE)
    c.line(18 * mm, H - 35 * mm, W - 18 * mm, H - 35 * mm)
    c.setFillColor(MUTED)
    c.setFont("Malgun", 7)
    c.drawString(18 * mm, 9 * mm, "T07 · 플랜두씨 다이어리 · 보안·네트워크 아키텍처")
    c.drawRightString(W - 18 * mm, 9 * mm, f"{page:02d} / 08")


def pill(x, y, text, color=BLUE):
    c.setFillColor(PALE)
    c.setStrokeColor(HexColor("#BFDBFE"))
    c.roundRect(x, y, 38 * mm, 9 * mm, 4.5 * mm, fill=1, stroke=1)
    c.setFillColor(color)
    c.setFont("Malgun-Bold", 8)
    c.drawCentredString(x + 19 * mm, y + 3 * mm, text)


# 1. Cover
c.setFillColor(NAVY)
c.rect(0, 0, W, H, fill=1, stroke=0)
c.setFillColor(BLUE)
c.rect(W * 0.67, 0, W * 0.33, H, fill=1, stroke=0)
c.setFillColor(HexColor("#60A5FA"))
c.setFont("Malgun-Bold", 10)
c.drawString(22 * mm, H - 25 * mm, "SKT FLY AI · ALEPH · T07")
c.setFillColor(WHITE)
c.setFont("Malgun-Bold", 31)
c.drawString(22 * mm, H - 55 * mm, "잠글 곳과 열어둘 곳을")
c.drawString(22 * mm, H - 70 * mm, "선으로 설명하다")
para("플랜두씨 다이어리의 네트워크, 인증 세션, 요청 보호, 소유권, 이관과 운영 증거", 22 * mm, H - 88 * mm, 155 * mm, 26 * mm, 13, HexColor("#CBD5E1"))
for i, (label, value) in enumerate([
    ("SESSION", "Access JWT + DB refresh session"),
    ("PASSWORD", "Argon2id · 19,456KiB · t=2 · p=1"),
    ("OBSERVATION", "2026-09-07 — 09-11 · 5 days"),
]):
    y = H - (42 + i * 43) * mm
    c.setFillColor(HexColor("#1D4ED8"))
    c.roundRect(W * 0.70, y, 72 * mm, 30 * mm, 4 * mm, fill=1, stroke=0)
    c.setFillColor(HexColor("#BFDBFE"))
    c.setFont("Malgun-Bold", 8)
    c.drawString(W * 0.70 + 6 * mm, y + 20 * mm, label)
    para(value, W * 0.70 + 6 * mm, y + 17 * mm, 60 * mm, 14 * mm, 9, WHITE, True)
c.setFillColor(HexColor("#94A3B8"))
c.setFont("Malgun", 8)
c.drawString(22 * mm, 16 * mm, "2026.09.11 · final architecture brief")
c.showPage()

# 2. Trust boundaries
header("01 · NETWORK", "요청은 세 경계를 통과한다", 2)
nodes = [
    (20, "브라우저", "React SPA\nSecure cookies"),
    (108, "Render", "TLS edge → Waitress\nFlask API + static"),
    (196, "Neon", "PostgreSQL\nuser/session/data"),
]
for x_mm, title, note in nodes:
    rect(x_mm * mm, 58 * mm, 70 * mm, 65 * mm, WHITE)
    c.setFillColor(BLUE)
    c.circle((x_mm + 9) * mm, 110 * mm, 3 * mm, fill=1, stroke=0)
    para(title, (x_mm + 16) * mm, 117 * mm, 48 * mm, 12 * mm, 14, INK, True)
    para(note, (x_mm + 8) * mm, 94 * mm, 54 * mm, 25 * mm, 10, MUTED)
for x in (92, 180):
    c.setStrokeColor(BLUE)
    c.setLineWidth(2)
    c.line(x * mm, 90 * mm, (x + 12) * mm, 90 * mm)
    c.line((x + 9) * mm, 93 * mm, (x + 12) * mm, 90 * mm)
    c.line((x + 9) * mm, 87 * mm, (x + 12) * mm, 90 * mm)
rect(20 * mm, 28 * mm, 246 * mm, 21 * mm, PALE, HexColor("#BFDBFE"))
para("공개 예외는 /api/live·/api/health뿐이다. SPA 하위 경로는 allowlist로만 셸을 반환하며, 오타 난 API는 404다.", 27 * mm, 44 * mm, 232 * mm, 12 * mm, 10, INK, True)
c.showPage()

# 3. Session
header("02 · SESSION", "서명과 서버 행을 함께 확인한다", 3)
steps = [
    ("1", "로그인", "Argon2id 검증\n없는 이메일은 dummy verify"),
    ("2", "세 쿠키", "Access · Refresh · CSRF\nURL·localStorage 사용 안 함"),
    ("3", "요청 가드", "JWT 서명·exp·sid·sub\nDB 세션 생존 확인"),
    ("4", "회전·폐기", "Refresh 매 사용 회전\n재사용 시 계열 폐기"),
]
for i, (num, title, note) in enumerate(steps):
    x = (18 + i * 68) * mm
    rect(x, 67 * mm, 57 * mm, 59 * mm, NAVY if i == 3 else WHITE, NAVY if i == 3 else LINE)
    para(f"STEP {num}", x + 6 * mm, 119 * mm, 45 * mm, 8 * mm, 8, HexColor("#60A5FA"), True)
    para(title, x + 6 * mm, 107 * mm, 45 * mm, 10 * mm, 14, WHITE if i == 3 else INK, True)
    para(note, x + 6 * mm, 90 * mm, 45 * mm, 20 * mm, 9, HexColor("#CBD5E1") if i == 3 else MUTED)
rect(18 * mm, 31 * mm, 125 * mm, 25 * mm, WHITE)
para("수명", 24 * mm, 51 * mm, 20 * mm, 8 * mm, 9, BLUE, True)
para("Access 10분 · 유휴 48시간 · 절대 14일", 47 * mm, 51 * mm, 88 * mm, 10 * mm, 10, INK, True)
rect(151 * mm, 31 * mm, 125 * mm, 25 * mm, WHITE)
para("즉시 로그아웃", 157 * mm, 51 * mm, 28 * mm, 8 * mm, 9, BLUE, True)
para("sid 세션 행 폐기 → 기존 Access도 401", 189 * mm, 51 * mm, 78 * mm, 10 * mm, 10, INK, True)
c.showPage()

# 4. Request protection
header("03 · REQUEST PROTECTION", "상태 변경은 세 겹으로 거른다", 4)
layers = [
    ("JSON", "단순 HTML form 모양 차단", "Content-Type application/json"),
    ("ORIGIN", "이 배포 출처만 허용", "Render TLS proxy scheme 반영"),
    ("CSRF", "읽을 수 있는 값만 헤더로 복사", "세션 쿠키 없이는 권한이 아님"),
]
for i, (title, headline, note) in enumerate(layers):
    x = (18 + i * 91) * mm
    rect(x, 69 * mm, 78 * mm, 58 * mm, WHITE)
    para(title, x + 6 * mm, 119 * mm, 64 * mm, 9 * mm, 9, BLUE, True)
    para(headline, x + 6 * mm, 105 * mm, 64 * mm, 14 * mm, 13, INK, True)
    para(note, x + 6 * mm, 84 * mm, 64 * mm, 11 * mm, 9, MUTED)
rect(18 * mm, 32 * mm, 260 * mm, 24 * mm, NAVY, NAVY)
para("정상 요청 2xx", 25 * mm, 51 * mm, 48 * mm, 9 * mm, 10, HexColor("#86EFAC"), True)
para("토큰 없음·불일치·교차 출처는 403", 80 * mm, 51 * mm, 85 * mm, 9 * mm, 10, HexColor("#FCA5A5"), True)
para("JSON 아님은 415", 176 * mm, 51 * mm, 55 * mm, 9 * mm, 10, HexColor("#FCD34D"), True)
para("GET/HEAD는 안전해야 하며, 상태를 바꾸는 GET은 만들지 않는다", 229 * mm, 51 * mm, 43 * mm, 12 * mm, 8, HexColor("#CBD5E1"))
c.showPage()

# 5. Ownership/data
header("04 · DATA OWNERSHIP", "클라이언트가 보낸 사용자 ID를 믿지 않는다", 5)
rect(18 * mm, 65 * mm, 76 * mm, 62 * mm, WHITE)
para("인증 가드", 25 * mm, 117 * mm, 60 * mm, 10 * mm, 14, INK, True)
para("JWT sub와 sid의 DB 소유자를 대조해 g.current_user를 만든다.", 25 * mm, 99 * mm, 60 * mm, 25 * mm, 9, MUTED)
rect(110 * mm, 65 * mm, 76 * mm, 62 * mm, PALE, HexColor("#BFDBFE"))
para("소유권 서비스", 117 * mm, 117 * mm, 60 * mm, 10 * mm, 14, INK, True)
para("plans_for · owned_plan · owned_task가 모든 조회 범위를 고정한다.", 117 * mm, 99 * mm, 60 * mm, 25 * mm, 9, MUTED)
rect(202 * mm, 65 * mm, 76 * mm, 62 * mm, NAVY, NAVY)
para("거절", 209 * mm, 117 * mm, 60 * mm, 10 * mm, 14, WHITE, True)
para("타인 ID는 존재 여부를 감추기 위해 읽기·수정·삭제 모두 404다.", 209 * mm, 99 * mm, 60 * mm, 25 * mm, 9, HexColor("#CBD5E1"))
for x in (98, 190):
    c.setStrokeColor(BLUE)
    c.setLineWidth(2)
    c.line(x * mm, 94 * mm, (x + 8) * mm, 94 * mm)
rect(18 * mm, 31 * mm, 260 * mm, 22 * mm, WHITE)
para("Export도 같은 경계", 25 * mm, 49 * mm, 42 * mm, 8 * mm, 9, BLUE, True)
para("계획·할 일·실행·완료·회고·규칙 변경을 현재 계정 범위의 단일 JSON으로 내보낸다.", 70 * mm, 49 * mm, 200 * mm, 10 * mm, 10, INK, True)
c.showPage()

# 6. Migration/deployment
header("05 · MIGRATION", "백업 → claim → NOT NULL 순서를 지킨다", 6)
milestones = [
    ("BACKUP", "Neon branch", "backup-20260905-before-t07-claim"),
    ("SCHEMA 1", "user_id nullable", "기존 T06 행을 먼저 읽을 수 있게"),
    ("CLAIM", "계획 3건", "고정 계정 소유권 부여 · 미소유 0"),
    ("SCHEMA 2", "user_id NOT NULL", "소유권 없는 새 행을 DB가 거절"),
    ("BOOT", "none", "일회성 작업 재실행 방지"),
  ]
for i, (tag, title, note) in enumerate(milestones):
    x = (12 + i * 56) * mm
    rect(x, 70 * mm, 48 * mm, 58 * mm, NAVY if i == 4 else WHITE, NAVY if i == 4 else LINE)
    para(tag, x + 5 * mm, 120 * mm, 38 * mm, 8 * mm, 8, HexColor("#60A5FA"), True)
    para(title, x + 5 * mm, 106 * mm, 38 * mm, 11 * mm, 12, WHITE if i == 4 else INK, True)
    para(note, x + 5 * mm, 88 * mm, 38 * mm, 15 * mm, 8, HexColor("#CBD5E1") if i == 4 else MUTED)
rect(18 * mm, 31 * mm, 260 * mm, 25 * mm, PALE, HexColor("#BFDBFE"))
para("운영 결과", 25 * mm, 51 * mm, 30 * mm, 8 * mm, 9, BLUE, True)
para("Alembic heads c48b1f60a2d7 + d5a3e91c7f20 · /api/live 200 · 익명 /api/auth/me 401", 59 * mm, 51 * mm, 210 * mm, 11 * mm, 10, INK, True)
c.showPage()

# 7. Evidence
header("06 · EVIDENCE", "실패를 포함한 결과를 같은 표에 남긴다", 7)
rows = [
    ("로그아웃 재사용", "200", "같은 쿠키 401"),
    ("타인 자료 읽기", "본인 200", "양방향 404"),
    ("타인 자료 변경", "본인 성공", "PATCH·DELETE 404"),
    ("Refresh 회전", "후계 1개", "이전 값 재사용 → 계열 폐기"),
    ("실제 관찰", "5 dates", "50/90 = 0.56배"),
]
para("장면", 22 * mm, 128 * mm, 60 * mm, 8 * mm, 9, MUTED, True)
para("성공", 100 * mm, 128 * mm, 55 * mm, 8 * mm, 9, GREEN, True)
para("거절·검산", 177 * mm, 128 * mm, 90 * mm, 8 * mm, 9, RED, True)
for i, (name, ok, denied) in enumerate(rows):
    y = (104 - i * 16) * mm
    rect(18 * mm, y, 260 * mm, 13 * mm, WHITE if i % 2 == 0 else PAPER)
    para(name, 24 * mm, y + 10 * mm, 66 * mm, 8 * mm, 9, INK, True)
    para(ok, 100 * mm, y + 10 * mm, 62 * mm, 8 * mm, 9, GREEN, True)
    para(denied, 177 * mm, y + 10 * mm, 93 * mm, 8 * mm, 9, RED if i < 4 else BLUE, True)
rect(18 * mm, 20 * mm, 260 * mm, 18 * mm, NAVY, NAVY)
para("최종 검사 319 passed · 3 PostgreSQL-only skips · frontend 76 passed · secret audit 0 findings", 25 * mm, 34 * mm, 246 * mm, 10 * mm, 10, WHITE, True)
c.showPage()

# 8. Limits
header("07 · LIMITS", "막지 않은 위험도 제출물에 포함한다", 8)
limits = [
    ("이메일 소유 확인 없음", "남의 주소로 가입 가능"),
    ("비밀번호 재설정 없음", "분실 시 계정 복구 불가"),
    ("가입 속도 제한 없음", "대량 계정 생성 가능"),
    ("회전 응답 유실", "이전 Refresh 재시도 시 재로그인"),
    ("세션 단위 폐기", "Access 하나만 선택 폐기 불가"),
    ("복잡도 규칙", "예측 가능한 치환을 유도할 수 있음"),
]
for i, (title, risk) in enumerate(limits):
    col, row = i % 3, i // 3
    x, y = (18 + col * 89) * mm, (81 - row * 45) * mm
    rect(x, y, 78 * mm, 36 * mm, WHITE)
    para(title, x + 6 * mm, y + 30 * mm, 65 * mm, 9 * mm, 11, INK, True)
    para(risk, x + 6 * mm, y + 17 * mm, 65 * mm, 9 * mm, 9, MUTED)
rect(18 * mm, 21 * mm, 256 * mm, 20 * mm, PALE, HexColor("#BFDBFE"))
para("범위 판단", 24 * mm, 37 * mm, 34 * mm, 8 * mm, 9, BLUE, True)
para("일반 사용자용 인증 서비스의 완성형이 아니라, 실패 경로와 한계를 재현 가능한 학습 구현으로 고정했다.", 61 * mm, 37 * mm, 204 * mm, 10 * mm, 10, INK, True)
c.showPage()

c.save()
print(OUT)
