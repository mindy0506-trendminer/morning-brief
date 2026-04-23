# Generate config/sources.yml from verified feed registry.
# Approved: 2026-04-21

from __future__ import annotations
import urllib.parse
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# -------- Section 1: English trade media (11) --------
en_trade = [
    # Existing alive (carried over)
    ("Business of Fashion", "https://www.businessoffashion.com/arc/outboundfeeds/rss/", "SpecializedMedia", "en", "GBR", "패션", "confirmed"),
    ("Retail Dive", "https://www.retaildive.com/feeds/news/", "TraditionalMedia", "en", "USA", "소비트렌드", "confirmed"),
    ("Skift", "https://skift.com/feed/", "TraditionalMedia", "en", "USA", "라이프스타일", "confirmed"),
    ("Food Dive", "https://www.fooddive.com/feeds/news/", "TraditionalMedia", "en", "USA", "식음료", "confirmed"),
    # Newly verified 2026-04-21
    ("WWD", "https://wwd.com/feed/", "SpecializedMedia", "en", "USA", "패션", "confirmed"),
    ("Glossy", "https://www.glossy.co/feed/", "SpecializedMedia", "en", "USA", "뷰티", "confirmed"),
    ("Modern Retail", "https://www.modernretail.co/feed/", "SpecializedMedia", "en", "USA", "소비트렌드", "confirmed"),
    ("Grocery Dive", "https://www.grocerydive.com/feeds/news/", "TraditionalMedia", "en", "USA", "식음료", "confirmed"),
    ("Restaurant Dive", "https://www.restaurantdive.com/feeds/news/", "TraditionalMedia", "en", "USA", "식음료", "confirmed"),
    ("Cosmetics Business", "https://www.cosmeticsbusiness.com/rss", "SpecializedMedia", "en", "GBR", "뷰티", "confirmed"),
    ("Dezeen", "https://www.dezeen.com/feed/", "SpecializedMedia", "en", "GBR", "라이프스타일", "confirmed"),
]

# -------- Section 2: Korean trade (3 new) --------
ko_trade = [
    ("식품외식경제", "https://www.foodbank.co.kr/rss/allArticle.xml", "TraditionalMedia", "ko", "KOR", "식음료", "confirmed"),
    ("뷰티경제", "https://www.thebk.co.kr/rss/allArticle.xml", "SpecializedMedia", "ko", "KOR", "뷰티", "confirmed"),
    ("장업신문", "https://www.jangup.com/rss/allArticle.xml", "SpecializedMedia", "ko", "KOR", "뷰티", "confirmed"),
]

# -------- Section 3: Spanish trade (2 new) --------
es_trade = [
    ("Modaes.es", "https://www.modaes.es/rss.xml", "SpecializedMedia", "es", "ESP", "패션", "confirmed"),
    ("Expansion Distribucion", "https://e00-expansion.uecdn.es/rss/empresas/distribucion.xml", "TraditionalMedia", "es", "ESP", "소비트렌드", "confirmed"),
]

# -------- Section 4: Chinese trade (carry over 2) --------
zh_trade = [
    ("36Kr", "https://36kr.com/feed", "TraditionalMedia", "zh", "CHN", "소비트렌드", "confirmed"),
    ("PANDAILY", "https://pandaily.com/feed/", "TraditionalMedia", "zh", "CHN", "소비트렌드", "confirmed"),
]


def gn_url(keyword: str, hl: str, gl: str) -> str:
    if hl == "zh-CN":
        ceid = "zh-Hans"
    elif "-" in hl:
        ceid = hl.split("-")[0]
    else:
        ceid = hl
    return (
        f"https://news.google.com/rss/search?q={urllib.parse.quote(keyword)}"
        f"&hl={hl}&gl={gl}&ceid={gl}:{ceid}"
    )


# -------- Section 5a: Google News KO existing broad (5 carry over) --------
gn_ko_existing = [
    ("Google News KR Food", "식품 OR 유통", "식음료"),
    ("Google News KR Beauty", "화장품 OR 뷰티", "뷰티"),
    ("Google News KR Fashion", "패션 OR 의류", "패션"),
    ("Google News KR Living", "리빙 OR 인테리어", "라이프스타일"),
    ("Google News KR Hospitality", "호텔 OR 여행", "라이프스타일"),
]

# -------- Section 5b: Google News KO category-specific keywords (24) --------
gn_ko_new = [
    ("식음료", "건강기능식품 OR 건기식"),
    ("식음료", "외식업 OR 프랜차이즈"),
    ("식음료", "편의점 OR 대형마트"),
    ("식음료", "대체육 OR 비건"),
    ("뷰티", "K뷰티 OR K-beauty"),
    ("뷰티", "화장품 신제품"),
    ("뷰티", "올리브영"),
    ("뷰티", "인디 뷰티"),
    ("패션", "럭셔리 OR 명품"),
    ("패션", "K패션"),
    ("패션", "스트리트패션 OR 스트릿"),
    ("패션", "리세일 OR 중고명품"),
    ("라이프스타일", "프리미엄 가전"),
    ("라이프스타일", "호캉스 OR 호텔"),
    ("라이프스타일", "인테리어 트렌드"),
    ("라이프스타일", "웰니스"),
    ("소비트렌드", "MZ세대 소비"),
    ("소비트렌드", "구독경제"),
    ("소비트렌드", "DTC"),
    ("소비트렌드", "가치소비"),
    ("MacroTrends", "ESG 소비재"),
    ("MacroTrends", "AI 리테일"),
    ("MacroTrends", "금리 소비"),
    ("MacroTrends", "인구 구조 소비"),
]

# -------- Section 5c: Google News JA (10, 5 cats x 2) --------
gn_ja = [
    ("식음료", "食品 トレンド"),
    ("식음료", "外食 チェーン"),
    ("뷰티", "化粧品 ブランド"),
    ("뷰티", "コスメ 新商品"),
    ("패션", "ファッション 業界"),
    ("패션", "ラグジュアリー 日本"),
    ("라이프스타일", "ホテル ニュース"),
    ("라이프스타일", "ライフスタイル ブランド"),
    ("소비트렌드", "Z世代 消費"),
    ("소비트렌드", "サブスク 消費"),
]

# -------- Section 5d: Google News ZH-Hans (10) --------
gn_zh = [
    ("식음료", "食品 消费"),
    ("식음료", "餐饮 品牌"),
    ("뷰티", "化妆品 品牌"),
    ("뷰티", "美妆 新品"),
    ("패션", "时尚 品牌"),
    ("패션", "奢侈品"),
    ("라이프스타일", "生活方式 品牌"),
    ("라이프스타일", "酒店 旅游"),
    ("소비트렌드", "Z世代 消费"),
    ("소비트렌드", "国潮"),
]

# -------- Section 5e: Google News ES (10) --------
gn_es = [
    ("식음료", "alimentacion tendencias"),
    ("식음료", "restaurante Espana"),
    ("뷰티", "belleza cosmetica"),
    ("뷰티", "skincare Espana"),
    ("패션", "moda Espana"),
    ("패션", "lujo Espana"),
    ("라이프스타일", "estilo de vida marca"),
    ("라이프스타일", "hotel viajes Espana"),
    ("소비트렌드", "consumo generacion Z"),
    ("소비트렌드", "DTC Espana"),
]

# -------- Section 5f: Google News EN (5) --------
gn_en = [
    ("소비트렌드", "gen z consumer trends"),
    ("소비트렌드", "subscription economy"),
    ("MacroTrends", "consumer sentiment index"),
    ("MacroTrends", "retail AI adoption"),
    ("MacroTrends", "ESG consumer goods"),
]

# -------- Section 6: Dead feeds (commented-out for history) --------
dead = [
    ("Vogue Business", "https://www.voguebusiness.com/rss", "en", "404 2026-04-21"),
    ("Hospitality Net", "https://www.hospitalitynet.org/rss/channel.rss", "en", "404 2026-04-21"),
    ("TrendWatching", "https://www.trendwatching.com/feed/", "en", "404 2026-04-21 — RSS discontinued"),
    ("Springwise", "https://www.springwise.com/feed/", "en", "403 2026-04-21 — Cloudflare"),
    ("Nikkei Business RSS", "https://www.nikkei.com/rss/topstories.rdf", "ja", "404 2026-04-21"),
    ("WWD Japan", "https://www.wwdjapan.com/feed", "ja", "403 2026-04-21 — login wall"),
    ("Fashionsnap", "https://www.fashionsnap.com/feed/", "ja", "404 2026-04-21"),
    ("Jing Daily", "https://jingdaily.com/feed/", "zh", "404 2026-04-21"),
    ("Modaes (legacy URL)", "https://www.modaes.com/feed.xml", "es", "404 2026-04-21 — replaced by modaes.es/rss.xml"),
    ("Food Retail", "https://www.foodretail.es/rss/portada", "es", "404 2026-04-21"),
    ("Marketing News ES", "https://www.marketingnews.es/rss", "es", "410 2026-04-21 — permanently gone"),
]


def emit_feed(name, url, src_type, lang, country, cat, status, out):
    cat_str = '"' + cat + '"' if cat else "null"
    out.append('  - name: "' + name + '"')
    out.append('    url: "' + url + '"')
    out.append("    source_type: " + src_type)
    out.append("    language: " + lang)
    out.append("    country: " + country)
    out.append("    category_hint: " + cat_str)
    out.append("    status: " + status)
    out.append("")


def emit_trade(entries, out):
    for row in entries:
        emit_feed(*row, out=out)


def emit_gn(gn_entries, hl, gl, lang, country, out, prefix_label):
    for cat, kw in gn_entries:
        name = f"{prefix_label} [{cat}] " + (kw[:40])
        url = gn_url(kw, hl, gl)
        emit_feed(name, url, "TraditionalMedia", lang, country, cat, "confirmed", out=out)


def emit_gn_existing(entries, out):
    for name, kw, cat in entries:
        emit_feed(name, gn_url(kw, "ko", "KR"), "TraditionalMedia", "ko", "KOR", cat, "confirmed", out=out)


def main():
    lines = []
    H = lines.append
    H("# =============================================================================")
    H("# morning-brief — RSS / keyword feed registry")
    H("# =============================================================================")
    H("# Last audit: 2026-04-21")
    H("# Coverage target: >=5 active feeds per category, >=90 daily unique stories")
    H("# Languages: ko, en, ja, zh, es (plan v2 sec A3)")
    H("#")
    H("# Sections:")
    H("#   1. English trade media (11)")
    H("#   2. Korean trade media (3)")
    H("#   3. Spanish trade media (2)")
    H("#   4. Chinese trade media (2)")
    H("#   5. Google News keyword feeds (KO 29 + JA 10 + ZH 10 + ES 10 + EN 5 = 64)")
    H("#   6. Commented-out dead feeds (historical reference)")
    H("# =============================================================================")
    H("")
    H("sources:")
    H("")

    H("  # ---------- 1. English trade media (verified 2026-04-21) ----------")
    H("")
    emit_trade(en_trade, lines)

    H("  # ---------- 2. Korean trade media (verified 2026-04-21) ----------")
    H("  # NOTE: 패션비즈 and 어패럴뉴스 have no public RSS endpoint as of audit;")
    H("  # their coverage is delegated to Google News KO keyword feeds in section 5.")
    H("")
    emit_trade(ko_trade, lines)

    H("  # ---------- 3. Spanish trade media (verified 2026-04-21) ----------")
    H("")
    emit_trade(es_trade, lines)

    H("  # ---------- 4. Chinese trade media (carried over) ----------")
    H("")
    emit_trade(zh_trade, lines)

    H("  # ---------- 5a. Google News KO (existing broad feeds) ----------")
    H("")
    emit_gn_existing(gn_ko_existing, lines)

    H("  # ---------- 5b. Google News KO (category-specific, 24) ----------")
    H("")
    emit_gn(gn_ko_new, "ko", "KR", "ko", "KOR", lines, "GN-KO")

    H("  # ---------- 5c. Google News JA (10) ----------")
    H("  # Japanese trade-media RSS all dead per audit; GN-JA covers the language.")
    H("")
    emit_gn(gn_ja, "ja", "JP", "ja", "JPN", lines, "GN-JA")

    H("  # ---------- 5d. Google News ZH-Hans (10) ----------")
    H("")
    emit_gn(gn_zh, "zh-CN", "CN", "zh", "CHN", lines, "GN-ZH")

    H("  # ---------- 5e. Google News ES (10) ----------")
    H("  # Spanish trade coverage is thin; GN-ES supplements Modaes.es and Expansion.")
    H("")
    emit_gn(gn_es, "es", "ES", "es", "ESP", lines, "GN-ES")

    H("  # ---------- 5f. Google News EN — soft trend / macro (5) ----------")
    H("")
    emit_gn(gn_en, "en-US", "US", "en", "USA", lines, "GN-EN")

    H("  # =============================================================================")
    H("  # 6. Commented-out DEAD feeds (audit 2026-04-21)")
    H("  # Preserved as comments so future RSS revival can be checked quickly.")
    H("  # =============================================================================")
    H("")
    for name, url, lang, reason in dead:
        H('  # - name: "' + name + '"    # DEAD ' + reason)
        H('  #   url: "' + url + '"')
        H("  #   language: " + lang)
        H("")

    with open("config/sources.yml", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    active = (
        len(en_trade)
        + len(ko_trade)
        + len(es_trade)
        + len(zh_trade)
        + len(gn_ko_existing)
        + len(gn_ko_new)
        + len(gn_ja)
        + len(gn_zh)
        + len(gn_es)
        + len(gn_en)
    )
    print(f"Wrote config/sources.yml")
    print(f"  Active feeds: {active}")
    print(f"  Dead (commented): {len(dead)}")
    print(f"  Breakdown:")
    print(f"    EN trade: {len(en_trade)}")
    print(f"    KO trade: {len(ko_trade)}")
    print(f"    ES trade: {len(es_trade)}")
    print(f"    ZH trade: {len(zh_trade)}")
    print(f"    GN-KO: {len(gn_ko_existing)}+{len(gn_ko_new)}={len(gn_ko_existing)+len(gn_ko_new)}")
    print(f"    GN-JA: {len(gn_ja)}")
    print(f"    GN-ZH: {len(gn_zh)}")
    print(f"    GN-ES: {len(gn_es)}")
    print(f"    GN-EN: {len(gn_en)}")


if __name__ == "__main__":
    main()
