""".docx şablonunu ilana özel CV içeriğiyle doldurur.

Üretilen Markdown CV (şablonla aynı bölüm yapısı) bölümlere ayrıştırılır ve şablona
<w:t> (metin düğümü) düzeyinde yazılır; böylece şablonun birebir biçimi — yazı tipleri,
boyutlar, aralıklar, kenar boşlukları, kalın etiketler ve proje başlığı köprüleri —
korunur. Fazladan kalın eklenmez: Markdown ** işaretleri düz metne indirilir, örnek CV ile
birebir eşleşir.

Dokunulmayan alanlar (fotoğraf, ad, slogan, iletişim satırı, "Software Developer -
Başlangıç Noktası" deneyimi ve Education bloğunun tamamı) hiç aranmaz; şablondaki gibi
aynen kalırlar.
"""
from __future__ import annotations

import copy
import io
import re

from docx import Document
from docx.oxml.ns import qn

from .config import CV_TEMPLATE_FILE

W_T = qn("w:t")
W_P = qn("w:p")
XML_SPACE = qn("xml:space")


# --------------------------------------------------------------------------- #
# Markdown parsing
# --------------------------------------------------------------------------- #

# İki işaret de bilerek kabul edilir. cv_base.md '*' ile yazılı, ama her Markdown biçimlendiricisi
# (bizi ısıran Prettier'ın format-on-save'iydi) listeyi '-'ye çevirir. Yalnızca '*' ile eşleşmek
# her maddenin ayrıştırmadan kaybolmasına yol açtı ve _fill_bullets() boş listede erken döner —
# yani üretilen maddeler yerine şablonun donmuş metni işverene sessizce gitti. Sondaki \s+ bir
# '**Bold**' satırının madde diye okunmasını engeller.
_BULLET_RE = re.compile(r"^[*-]\s+")


def _is_md_bullet(line: str) -> bool:
    return _BULLET_RE.match(line) is not None


def _bullet_text(line: str) -> str:
    return _strip_md(_BULLET_RE.sub("", line).strip())


def _strip_md(text: str) -> str:
    """Markdown kalın/italik işaretlerini ve sondaki <br>'yi siler, düz metin döndürür.

    ** (kalın) ve * (italik, ör. ``*(Ongoing)*``) silinir ki Google Doc'a hiçbir işaret
    sızmasın; Doc örnek CV ile fazladan vurgu olmadan birebir eşleşmeli.
    """
    text = text.replace("<br>", "").replace("**", "").replace("*", "")
    return text.strip()


# '#' işaretleri kalın içine alınmış olabilecek bir başlık: '### SUMMARY', '#### [Title](url)',
# ve — ADIM 10 takas edilen bir projenin eklediği her kelimeyi kalın yaptığı için —
# '**#### [Title](url)**'. Çıplak bir '#'e çapalamak proje bloğunun tamamını (başlık, maddeler VE
# tech satırı) ayrıştırmadan sessizce düşürdü, yerine şablonun donmuş yuvası gitti: cv_322'nin PDF'i
# API Hotel Project'i kaybetti ve Cloud File Storage'ı iki kez listeledi.
_HEADING_RE = re.compile(r"^(?:\*\*)?(#{3,4})\s+(.+)$")


def _heading(line: str):
    """('### '/'#### ' seviyesi, başlık metni) ya da None. '#' etrafındaki kalın işaretleri tolere edilir."""
    m = _HEADING_RE.match(line)
    return (len(m.group(1)), m.group(2).strip()) if m else None


_TITLE_LINK_RE = re.compile(r"^\[(?P<disp>.+?)\]\((?P<url>[^)\s]+)\)(?P<rest>.*)$")


def _parse_title_link(text: str):
    """Bir proje başlığı '[Display](https://github.com/...)' -> (display_text, url).

    Link yoksa (plain_title, "") döner. Önce kalın/italik işaretleri silinir; böylece
    '**[Display](url)**' gibi kalına sarılmış bir başlık da ayrıştırılır — yoksa baştaki '**'
    ^\\[ çapasını bozar, URL kaybolur ve yuva sessizce şablonun orijinal (yanlış) köprüsünü tutar.
    """
    m = _TITLE_LINK_RE.match(_strip_md(text))
    if m:
        display = (m.group("disp") + m.group("rest")).strip()
        return _strip_md(display), m.group("url").strip()
    return _strip_md(text), ""


def parse_markdown_cv(md: str) -> dict:
    """Üretilen CV Markdown'unu yapılandırılmış, düz metin bölümlere ayrıştırır."""
    lines = md.splitlines()
    section = None
    summary: list[str] = []
    core_skills: list[str] = []
    experience: list[dict] = []
    previous_exp: list[str] = []
    projects: list[dict] = []
    cur_entry: dict | None = None
    cur_project: dict | None = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        heading = _heading(stripped)
        if heading and heading[0] == 3:
            section = _strip_md(heading[1]).upper()
            cur_project = None
            cur_entry = None
            continue
        if not stripped:
            continue
        if section is None:
            # İlk "### " başlığından önceki her önsözü yok say. Bu olmadan "### SUMMARY"den önceki başıboş
            # bir satır aşağıdaki section.startswith() kontrolüne ulaşır ve şu hatayla çöker:
            # 'NoneType' object has no attribute 'startswith'.
            continue

        if section == "SUMMARY":
            summary.append(_strip_md(stripped))

        elif section == "CORE SKILLS":
            core_skills.append(_strip_md(stripped))

        elif section == "EXPERIENCE":
            if heading and heading[0] == 4:
                cur_entry = {"title": _strip_md(heading[1]), "bullets": []}
                experience.append(cur_entry)
            elif cur_entry is not None and _is_md_bullet(stripped):
                cur_entry["bullets"].append(_bullet_text(stripped))

        elif section == "SELECTED PROJECTS":
            if heading and heading[0] == 4:
                disp, url = _parse_title_link(heading[1])
                cur_project = {"title": disp, "title_url": url, "bullets": [], "tech": ""}
                projects.append(cur_project)
            elif cur_project is not None:
                # 'Tech:' testinden ÖNCE işaretleri sil. ADIM 10 modele cv_base.md'den farklı her kelimeyi kalın
                # yaptırır; yani ADIM 8'de takas edilen bir proje tamamen kalın gelir — '**Tech: Python, FastAPI, ...**'.
                # Ham satırla eşleşmek tech'i boş bıraktı, build_docx boş tech'i atlar ve şablonun donmuş Tech satırı
                # (ÖNCEKİ projenin stack'i) Markdown doğru görünürken .docx/PDF'e gitti. _parse_title_link'in
                # belgelediği tuzağın aynısı.
                plain = _strip_md(stripped)
                if plain.lower().startswith("tech:"):
                    cur_project["tech"] = plain.split(":", 1)[1].strip()
                elif _is_md_bullet(stripped):
                    cur_project["bullets"].append(_bullet_text(stripped))

        elif section.startswith("PREVIOUS EXPERIENCE"):
            # Rol başlığı artık başlık satırında; buradaki her satır açıklamadır.
            previous_exp.append(_strip_md(stripped))

    return {
        "summary": " ".join(summary).strip(),
        "core_skills": core_skills,
        # Belge sırasıyla her EXPERIENCE girdisi, her biri {title, bullets}. Hepsi şablona doldurulur —
        # bkz. build_docx.
        "experience": experience,
        "projects": projects,
        # Rol başlığı artık başlık satırında; toplanan bütün satırlar açıklamadır.
        "previous_exp_desc": " ".join(previous_exp).strip(),
    }


# --------------------------------------------------------------------------- #
# Düşük seviye docx yardımcıları (bütün biçimi korumak için <w:t> düğümleri üzerinde çalışır)
# --------------------------------------------------------------------------- #

def _t_nodes(p) -> list:
    """Bir paragraftaki bütün <w:t> metin düğümleri, belge sırasıyla (köprüler dahil)."""
    return p._p.findall(".//" + W_T)


def _para_text(p) -> str:
    return "".join((t.text or "") for t in _t_nodes(p))


def _set_node(node, text: str) -> None:
    node.text = text
    node.set(XML_SPACE, "preserve")


def _replace_content(p, new_text: str, keep_prefix_nodes: int = 0) -> None:
    """new_text'i ilk içerik metin düğümüne koyar, sonraki içerik düğümlerini temizler.

    keep_prefix_nodes: dokunulmadan bırakılacak baştaki <w:t> düğümü sayısı (ör. 'Backend:'
    gibi kalın bir etiket, bir madde işareti '• ' ya da 'Tech:').
    """
    nodes = _t_nodes(p)
    if len(nodes) <= keep_prefix_nodes:
        return
    content_nodes = nodes[keep_prefix_nodes:]
    # Etiket düğümü boşlukla bitmiyorsa baştaki boşluğu koru.
    prefix_text = nodes[keep_prefix_nodes - 1].text if keep_prefix_nodes else ""
    lead = " " if (prefix_text and not prefix_text.endswith(" ")) else ""
    _set_node(content_nodes[0], lead + new_text)
    for n in content_nodes[1:]:
        _set_node(n, "")


def _set_bullet_text(p, text: str) -> None:
    """Bir madde paragrafının metnini ayarlar; '• ' işaretini ve node[0] biçimini korur.

    İki şablon yerleşimini de işler: işaret+metin tek bir <w:t> düğümünde, ya da '• ' ve içerik
    iki düğüme bölünmüş. Her şeyi ilk düğümde birleştiririz (maddeler düz, kalın değil; bu
    birebir görünümü korur).
    """
    nodes = _t_nodes(p)
    if not nodes:
        return
    _set_node(nodes[0], "• " + text)
    for n in nodes[1:]:
        _set_node(n, "")


def _set_hyperlink_target(p, url: str) -> None:
    """Paragrafın köprüsünü (ör. bir proje başlığı) `url`'ye yönlendirir."""
    hl = p._p.find(qn("w:hyperlink"))
    if hl is None:
        return
    rid = hl.get(qn("r:id"))
    rels = p.part.rels
    if rid and rid in rels:
        rels[rid]._target = url


def _is_bullet(p) -> bool:
    return _para_text(p).lstrip().startswith("•")


def _is_tech(p) -> bool:
    return _para_text(p).strip().lower().startswith("tech:")


def _clone_after(p):
    """p paragrafının derin kopyasını alır ve kopyayı hemen arkasına ekler. Yeni CT_P'yi döndürür."""
    new_p = copy.deepcopy(p._p)
    p._p.addnext(new_p)
    return new_p


def _remove(p_elem) -> None:
    p_elem.getparent().remove(p_elem)


# --------------------------------------------------------------------------- #
# Section fillers
# --------------------------------------------------------------------------- #

def _find_header(paragraphs, prefix: str) -> int:
    for i, p in enumerate(paragraphs):
        if _para_text(p).strip().upper().startswith(prefix):
            return i
    raise ValueError(f"Header not found: {prefix}")


def _fill_bullets(bullet_paras: list, new_bullets: list[str]) -> None:
    """Madde paragraflarının sayısını new_bullets'a eşitler, sonra metinlerini ayarlar.

    bullet_paras: şablonda var olan madde Paragraph nesneleri (>=1). Madde işareti ('• ')
    ilk metin düğümünde durur ve korunur.
    """
    if not bullet_paras or not new_bullets:
        return

    from docx.text.paragraph import Paragraph

    parent = bullet_paras[0]._parent
    elems = [bp._p for bp in bullet_paras]

    # Büyüt: son madde öğesini gerektiği kadar klonla.
    while len(elems) < len(new_bullets):
        last = elems[-1]
        new_el = copy.deepcopy(last)
        last.addnext(new_el)
        elems.append(new_el)
    # Shrink: remove extra bullet elements.
    while len(elems) > len(new_bullets):
        _remove(elems.pop())

    for el, text in zip(elems, new_bullets):
        _set_bullet_text(Paragraph(el, parent), text)


def _fill_core_skills(skill_paras: list, lines: list[str]) -> None:
    """'Etiket: içerik' beceri paragraflarını doldurur, Markdown satırı başına bir tane.

    Şablon sabit sayıda yuvayla gelir, ama CV meşru olarak farklı sayıda beceri satırı
    taşıyabilir (saf back-end ilanında Frontend satırı çıkarılır); bu yüzden yuvalar madde
    listeleri gibi büyütülür/küçültülür. Kalın ETİKET de Markdown'dan alınır: yalnızca içeriği
    doldurmak, bir satır eklendiği ya da çıkarıldığı anda her satırı şablonun orijinal
    etiketinin altına sessizce kaydırırdı.
    """
    if not skill_paras or not lines:
        return

    from docx.text.paragraph import Paragraph

    parent = skill_paras[0]._parent
    elems = [p._p for p in skill_paras]

    while len(elems) < len(lines):
        new_el = copy.deepcopy(elems[-1])
        elems[-1].addnext(new_el)
        elems.append(new_el)
    while len(elems) > len(lines):
        _remove(elems.pop())

    for el, line in zip(elems, lines):
        p = Paragraph(el, parent)
        nodes = _t_nodes(p)
        if not nodes:
            continue
        label, sep, content = line.partition(":")
        if not sep:  # bu satırda etiket yok: hepsini içerik düğümüne koy
            _replace_content(p, line.strip(), keep_prefix_nodes=0)
            continue
        _set_node(nodes[0], f"{label.strip()}:")
        _replace_content(p, content.strip(), keep_prefix_nodes=1)


def _shrink_trailing_empty_paragraph(doc) -> None:
    """Belgenin sonundaki boş paragrafı 1pt'ye indirir.

    Şablon PREVIOUS EXPERIENCE açıklamasından sonra varsayılan boyutta boş bir paragrafla biter.
    İçerik sayfanın son satırına kadar inince bu görünmez satır sığmaz ve Google'ın PDF'i ikinci,
    BOMBOŞ bir sayfa taşır (cv_371 böyle çıktı; ölçüm 2026-10-23). Paragraf silinmez — Word ve
    Google Docs belgenin bir paragrafla bitmesini bekler — yalnızca yüksekliği sıfıra yaklaştırılır.
    """
    from docx.enum.text import WD_LINE_SPACING
    from docx.shared import Pt

    last = doc.paragraphs[-1]
    if _para_text(last).strip():
        return
    pf = last.paragraph_format
    pf.space_before = pf.space_after = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(1)
    for run in last.runs:
        run.font.size = Pt(1)
    # Boş paragrafın yüksekliğini run'lar değil paragraf işaretinin (pPr/rPr) boyutu belirler.
    ppr = last._p.get_or_add_pPr()
    rpr = ppr.find(qn("w:rPr"))
    if rpr is None:
        rpr = ppr.makeelement(qn("w:rPr"), {})
        ppr.append(rpr)
    for tag in ("w:sz", "w:szCs"):
        for old in rpr.findall(qn(tag)):
            rpr.remove(old)
        rpr.append(rpr.makeelement(qn(tag), {qn("w:val"): "2"}))  # yarım punto: 2 = 1pt


def build_docx(markdown_cv: str) -> bytes:
    """Bir .docx (bayt) döndürür = ilana özel CV içeriğiyle doldurulmuş şablon."""
    data = parse_markdown_cv(markdown_cv)
    doc = Document(str(CV_TEMPLATE_FILE))
    paras = doc.paragraphs

    # --- SUMMARY: SUMMARY başlığından sonraki ilk boş olmayan paragraf ---
    i = _find_header(paras, "SUMMARY")
    for p in paras[i + 1:]:
        if _para_text(p).strip():
            _replace_content(p, data["summary"], keep_prefix_nodes=0)
            break

    # --- CORE SKILLS: one 'Label: content' line per markdown skill line ---
    cs_start = _find_header(paras, "CORE SKILLS")
    exp_start = _find_header(paras, "EXPERIENCE")
    skill_paras = [p for p in paras[cs_start + 1: exp_start] if _para_text(p).strip()]
    _fill_core_skills(skill_paras, data["core_skills"])

    # Yukarıda yuvalar eklenmiş/çıkarılmış olabilir; paragraf listesini yeniden oku.
    paras = doc.paragraphs
    exp_start = _find_header(paras, "EXPERIENCE")

    # --- EXPERIENCE: HER girdinin maddelerini sırayla doldur ---
    # Girdi başlıkları bilerek DOLDURULMAZ: şablonun ifadesi tasarlanmış olandır (ör. tarihi
    # "Jun – Aug 2025" diye aralıklı yazar, cv_base.md ise "Jun–Aug 2025" yazar) ve şimdiye kadar
    # üretilen her CV'de Markdown başlıkları cv_base.md ile birebir aynı — yani kopyalanacak bir şey
    # yok, kaybedilecek bir şey var.
    proj_start = _find_header(paras, "SELECTED PROJECTS")
    entry_slots: list[list] = []  # madde paragrafları, girdi başına bir liste, sırayla
    cur_slot: list | None = None
    for p in paras[exp_start + 1: proj_start]:
        if not _para_text(p).strip():
            continue
        if not _is_bullet(p):  # bir girdi başlık satırı yeni bir girdi açar
            cur_slot = []
            entry_slots.append(cur_slot)
        elif cur_slot is not None:
            cur_slot.append(p)
    # Bir girdiyi büyütmek/küçültmek yalnızca kendi başlığı ile sonrakinin arasındaki öğelere dokunur;
    # böylece sonraki girdilerin Paragraph nesneleri geçerli kalır.
    for slot, entry in zip(entry_slots, data["experience"]):
        _fill_bullets(slot, entry["bullets"])

    # --- SELECTED PROJECTS: her proje yuvasını sırayla doldur ---
    edu_start = _find_header(paras, "EDUCATION")
    # Bölgeyi bloklara ayır: her blok madde/tech olmayan bir başlık satırıyla başlar.
    blocks: list[dict] = []
    cur: dict | None = None
    for p in paras[proj_start + 1: edu_start]:
        if not _para_text(p).strip():
            continue
        if _is_bullet(p):
            if cur:
                cur["bullets"].append(p)
        elif _is_tech(p):
            if cur:
                cur["tech"] = p
        else:  # title line
            cur = {"title": p, "bullets": [], "tech": None}
            blocks.append(cur)

    # Dolduracak projesi olmayan bir yuva aksi halde şablonun donmuş içeriğini tutardı — modelin
    # bilerek çıkardığı bir proje, kullanıcının incelediği CV'nin altında gönderilirdi (ve çıkarma bir
    # ayrıştırma hatasıysa, projeyi önceki yuvada çoğaltırdı). Bunun yerine fazla yuvaları sil. Burada
    # büyütme yok: Markdown'da asla şablondaki yuvalardan FAZLA proje olmaz ve olsaydı fazla proje
    # sessizce kaybolurdu.
    for slot in blocks[len(data["projects"]):]:
        for p in [slot["title"], *slot["bullets"]] + ([slot["tech"]] if slot["tech"] is not None else []):
            _remove(p._p)

    for slot, proj in zip(blocks, data["projects"]):
        _replace_content(slot["title"], proj["title"], keep_prefix_nodes=0)
        if proj.get("title_url"):
            _set_hyperlink_target(slot["title"], proj["title_url"])
        if slot["bullets"]:
            _fill_bullets(slot["bullets"], proj["bullets"])
        if slot["tech"] is not None and proj["tech"]:
            _replace_content(slot["tech"], proj["tech"], keep_prefix_nodes=1)

    # --- PREVIOUS EXPERIENCE: rol başlığı artık başlık satırında; yani başlıktan sonraki ilk boş
    # olmayan paragraf açıklamanın kendisidir. ---
    if data["previous_exp_desc"]:
        pe_start = _find_header(paras, "PREVIOUS EXPERIENCE")
        for p in paras[pe_start + 1:]:
            if _para_text(p).strip():
                _replace_content(p, data["previous_exp_desc"], keep_prefix_nodes=0)
                break

    _shrink_trailing_empty_paragraph(doc)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
