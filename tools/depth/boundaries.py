#!/usr/bin/env python3
"""Глубина формализации по статьям: уровни §33.1, вычисленные из CLIR.

Прежняя версия считала статью «затронутой» при наличии фрагмента и на этом
останавливалась. Мера сломалась ровно тогда, когда стала нужна: у ОСМС после
заведения фрагментов на все статьи она показала 42/42 и замолчала — а
различие осталось, и оно принципиальное. Из двенадцати статей выводятся
суммы, сроки, пеня и статус; из остальных тридцати не выводится ничего, там
описательные факты. Одно число «42/42» это скрывало.

§33.1 требует считать text/semantic/executable coverage РАЗДЕЛЬНО и прямо
запрещает выдавать «100 % формализовано», когда часть фрагментов имеет только
`SOURCE_ONLY`. Уровни вычисляются из документа, а не размечаются автором:
разметка руками означала бы, что ошибка автора молча меняет отчёт о полноте —
то самое утверждение, ради честности которого раздел существует.

Что считается:

  EXECUTABLE   на статью ссылается правило — из неё что-то ВЫВОДИТСЯ
  INTERPRETED  правило есть, но `include` §152 вывел его из базовой теории:
               без выбранного прочтения вывода нет ни на одном деле
  ANCHORED     ссылается семантический узел, но не правило (нормативные
               факты §71, closure) — адресуемо и применимо к вопросу,
               но вывода нет
  SOURCE_ONLY  фрагмент есть, ни один узел на статью не ссылается —
               «текст сохранён и адресуем» и только
  EXCLUDED     единица прямо исключена из измеряемой временной редакции —
               хранится в источнике и карте, но не считается отсутствующей
  —            ни фрагмента, ни ссылки: статья вне пакета

Уровни `STRUCTURED`, `SEMANTIC` и `VERIFIED` §33.1 здесь НЕ выставляются:
отличить их по виду узла нельзя, а придумать отображение — та же авторская
разметка, только спрятанная в инструмент. Их отсутствие честнее подмены.

ОГОВОРКА О РАЗРЕШЕНИИ ЯКОРЕЙ. §33 ожидает, что якорь — StableId фрагмента.
Корпус ссылается строками внешнего реестра (`KZ-OSMS-405-V-ART-26-1`), и
номер статьи достаётся из них соглашением об именовании. Пока это так, мера
зависит от соглашения: якорь, названный иначе, будет не разрешён, и статья
покажется менее покрытой, чем есть. Число неразрешённых печатается.

  boundaries.py <акт>                  — например: boundaries.py osms
  boundaries.py <ru.txt> <clir.json>   — явные пути
  boundaries.py --all                  — все акты с закреплённым источником
"""
from __future__ import annotations
# Structural measurement can run on a selected tool snapshot without installing
# an evaluator. Temporal grouping for text editions still uses the pinned runtime
# lazily; intrinsic CNXML divisions use the exact hashed publication edition.
import pathlib as _law_split_pathlib
import sys as _law_split_sys
_law_split_lib = next(
    (parent / "corpus" / "tools" / "lib" for parent in _law_split_pathlib.Path(__file__).resolve().parents
     if (parent / "corpus" / "tools" / "lib" / "act_split.py").is_file()
     and not (parent / "corpus" / "tools" / "lib" / "act_split.py").is_symlink()),
    None,
)
if _law_split_lib is None:
    raise RuntimeError("cannot find corpus/tools/lib/act_split.py from this script path")
ROOT = _law_split_lib.parents[2]
_law_split_lib_text = str(_law_split_lib)
if _law_split_lib_text not in _law_split_sys.path:
    _law_split_sys.path.insert(0, _law_split_lib_text)
del _law_split_lib_text, _law_split_lib, _law_split_pathlib, _law_split_sys

import hashlib
import json
import re
import sys
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 used by the repository CI launcher.
    import tomli as tomllib
from pathlib import Path

sys.path.insert(0, str(ROOT / "corpus" / "lib"))


def is_applicable(edition: dict, time: str) -> bool:
    """Reuse the pinned applicability machine only when temporal grouping needs it."""
    import lawbin
    sys.path.insert(0, str(lawbin.lawref_site_packages()))
    from lawref.editions.applicability import is_applicable as evaluate
    return evaluate(edition, time)


# Разрез текста на единицы деления перенесён в `corpus/tools/lib/act_split.py`
# (DECISION-0067): его читают леджер предложений и его ворота, а импорт скиллом
# из corpus/tools честнее импорта воротами из `.claude/`. Здесь остались
# разрешатель путей акта и сама мера `depth()`; все перенесённые имена
# реэкспортируются, поэтому потребители (`test_boundaries.py`, скилл
# audit-formalization, ворота глубины) не правились. Перенос сверен байтово:
# выход `boundaries.py --all` до и после идентичен.
sys.path.insert(0, str(ROOT / "corpus" / "tools" / "lib"))
from act_split import (  # noqa: E402,F401
    ANCHOR_ARTICLE_RE,
    ARTICLE_CONVENTIONS,
    ARTICLE_RE,
    ARTICLE_ROMAN_RE,
    DECLARED_CONVENTIONS,
    EN_ARTICLE_ROMAN_RE,
    FR_ARTICLE_RE,
    LOCATOR_RE,
    PARAGRAPH_UNITS,
    POLICY_SECTION_RE,
    PRINCIPLE_RE,
    SECTION_RE,
    TABULA_ITEM_RE,
    VERSE_RE,
    YAR_RULE_RE,
    CNXML_UNITS,
    OPENSTAX_SECTION_UNIT,
    article_matches,
    article_spans,
    irregular_heads,
    locator_unit,
    locator_units,
    marginal_heads,
    ordinal_heads,
    policy_section_heads,
    principle_heads,
    roman_to_int,
    tabula_item_heads,
    verse_heads,
    word_heads,
    yar_rule_heads,
)

#: Виды узлов, наличие которых делает статью EXECUTABLE: из неё выводят —
#: либо ПРОВЕРЯЮТ её на каждом деле.
#:
#: `constraint` вписан 02.09.2026 по решению владельца. До errata E-0086
#: констрейнт §93.1 не исполнялся вовсе (ни статуса, ни узла, ни issue), и
#: держать его вне этого множества было верно: объявление без исполнения
#: ничего о статье не обещает. После E-0086 он вычисляется при КАЖДОМ
#: evaluation, даёт результат `CONSTRAINT` со статусом SATISFIED/VIOLATED,
#: узел `constraint_check` и issue — то есть статья под констрейнтом
#: отвечает на деле, а не просто адресуема.
#:
#: ЧТО ЭТО МЕНЯЕТ В ЧТЕНИИ МЕРЫ. `EXECUTABLE` теперь означает «из единицы
#: выводится ЛИБО единица проверяется», и два эти случая внутри уровня не
#: различаются. Разница между ними реальна — констрейнт по §93.1 опоры не
#: даёт и правового последствия не создаёт, — поэтому акт, где ВСЯ норма
#: выражена проверками, обязан говорить это словами в своём отчёте, а не
#: прятать за общим числом (образец — `corpus/laws/doctrine/accounting/pacioli-computis/
#: audit.ru.md`, раздел о повторном аудите).
#:
#: ИЗМЕРЕННЫЙ РАДИУС правки на 02.09.2026: единицы под ОДНИМИ констрейнтами
#: есть у четырёх актов корпуса — `it-pacioli-computis` (18 глав),
#: `eu-ifrs-16-leases` (5), `eu-ifrs-15-revenue` (3), `eo-fundamento` (1),
#: всего 27 единиц. У остальных актов мера не двинулась: они либо не
#: используют констрейнты, либо ставят их на статьи, где есть и правила.
DERIVING_KINDS = {"rule", "priority_rule", "closure_policy", "norm_template",
                  "constraint"}


def is_position_node(node: dict) -> bool:
    """Позиционные мосты не являются глубиной формализации статьи.

    `Position*` — служебные узлы корпуса для трассировки позиций, а не
    самостоятельные выводящие нормы §33.1. Их якоря не должны превращать
    статью в EXECUTABLE и не должны конкурировать с якорем обычного
    semantic node (relation, external relation и т. п.).
    """
    node_id = str(node.get("id", ""))
    return node_id.rsplit("#", 1)[-1].startswith("Position")


def interpretation_gated(nodes: list[dict]) -> set[str]:
    """Узлы, выведенные из БАЗОВОЙ ТЕОРИИ гейтом толкования §152/§157.

    Правило с непустой интерпретационной принадлежностью активно ТОЛЬКО при
    выбранном прочтении: без выбора `resolve_interpretations` вычёркивает его
    ДО всякого исполнения. Мера, засчитывающая такое правило в `EXECUTABLE`,
    обещает вывод, которого на обычном деле нет ни одного, — и обещает его
    ГРОМЧЕ всех прочих чисел отчёта, потому что `EXECUTABLE` есть высший
    уровень §33.1. Измерено 29.08.2026 на Регламенте (ЕС) 261/2004: четыре
    статьи стояли `EXECUTABLE`, пока их обязанностей не существовало.

    Принадлежность считается ТАК ЖЕ, как её считает оракул: объединение поля
    `interpretations` узла (§101) и `includes` каждой интерпретации (§152), с
    композицией `extends`/`excludes` (§157). Композиция повторена здесь, а не
    импортирована из `lawref`, по единственной причине: скилл обязан работать
    без `PYTHONPATH=engines/lawref`, и `verify/ci/gates/silence/check_interpretation_gate.py` держит обе
    стороны сверенными — он читает ту же принадлежность из оракула и падает,
    если множества разойдутся.
    """
    interps = {str(n.get("id", "")): n for n in nodes
               if n.get("kind") == "interpretation"}

    def members(iid: str, seen: frozenset[str] = frozenset()) -> set[str]:
        node = interps.get(iid)
        if node is None or iid in seen:
            return set()
        out = {str(x) for x in node.get("includes", []) or []}
        for parent in node.get("extends", []) or []:
            out |= members(str(parent), seen | {iid})
        return out - {str(x) for x in node.get("excludes", []) or []}

    gated: set[str] = set()
    for node in nodes:
        if node.get("interpretations"):
            gated.add(str(node.get("id", "")))
    for iid in interps:
        gated |= members(iid)
    return gated


def act_declaration(act: str) -> Path | None:
    """Карта статей акта в старой либо многофайловой раскладке."""
    # Доманифестного кандидата `corpus/laws/sources/<акт>/articles.json` здесь
    # больше нет: каталог удалён 29.08.2026, и его исчезновение — объявленный
    # DECISION-0033 §6 критерий завершения миграции корпуса. До удаления он
    # держал две УСТАРЕВШИЕ копии и стоял первым кандидатом.
    candidates: list[Path] = []
    # Каталог берётся `act_dir`, а не склейкой `corpus/laws/<акт>`: у акта на
    # втором и глубже уровне склейка даёт несуществующий путь, карта не
    # находится, и `act_source` возвращает None — что читается как «фаза 0 не
    # выполнена». Наблюдалось на подпакетах Конституции.
    package = act_dir(act)
    own: set[str] = set()
    if package is not None and package.is_dir():
        # У пакета может быть НЕСКОЛЬКО закреплённых документов: собственный
        # текст акта плюс то, на что он ссылается несущим образом (мирные
        # собрания держат ещё и НП КС 61-НП). Алфавитный порядок брал чужую
        # карту, и акт выпадал из меры МОЛЧА: у постановления нет заголовков
        # «Статья N», мера возвращала ноль строк, а ноль строк читается как
        # «мера неприменима». Собственная карта — та, чей каталог назван
        # именем акта; остальные измеряются явной парой аргументов.
        # Каталог закреплённых байтов зовётся ПРОСТЫМ именем акта
        # (`sources/osms/`), а сам акт при вложенности — путём (`kz-osms`).
        # Своей считается карта, чей каталог назван любым из двух.
        own = {act, package.name}
        found = sorted(package.glob("sources/**/articles.json"))
        candidates.extend(sorted(found, key=lambda path: path.parent.name not in own))

    def has_documents(path: Path) -> bool:
        """Карта, рядом с которой лежат объявленные ею байты."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        names = [payload["document"]] if payload.get("document") else [
            e.get("document") for e in payload.get("editions", []) if e.get("document")]
        names = [n for n in names if n] or list(SOURCE_DOCUMENTS)
        return any((path.parent / name).is_file() for name in names)

    # Карта без своих байтов уступает той, у которой они есть. Правило заведено
    # 28.08.2026 против доманифестного пути, который у Конституции пережил
    # миграцию ПУСТЫМ и забирал акт себе: карта нашлась, документов рядом нет,
    # `act_source` возвращает None, а None читается как «фаза 0 не выполнена».
    # Путь удалён, но правило осталось: у пакета законно бывает несколько карт.
    files = [path for path in candidates if path.is_file()]
    present = [path for path in files if has_documents(path)]

    # У одного пакета могут лежать карта действующего акта и карта
    # исторического источника, нужного лишь для переходного сценария. Простая
    # лексикографическая сортировка тогда измеряет старый текст: у income-tax
    # это выбирало `tax-code-2017` перед полным учётом `tax-code-2025` и
    # превращало 848 статей действующего Кодекса в 800 строк «вне пакета».
    # `scope: whole` — явное авторское объявление, что карта покрывает весь
    # документ, поэтому при нескольких пригодных картах она и есть первичный
    # объект меры. Для пакетов без такой карты сохраняется прежний стабильный
    # порядок; менять первичный документ догадкой о годе нельзя.
    #
    # Форма `{"editions": [...]}` (DECISION-0026) объявляет `scope` У КАЖДОЙ
    # редакции, и верхнего уровня у такого файла нет вовсе — `.get("scope")`
    # отвечал по ней `None`, то есть карта в форме редакций не считалась
    # полной НИКОГДА. Четвёртый случай одной слепоты: так же не читались
    # `document` (`act_source`), объявленные границы (гейт глубины) и `unit`.
    def whole_scope(path: Path) -> bool:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "editions" in payload:
            editions = payload["editions"]
            return bool(editions) and all(
                edition.get("scope") == "whole" for edition in editions)
        return payload.get("scope") == "whole"

    # Полнота охвата — критерий ВТОРОЙ, а собственность карты первый. Порознь
    # они и разошлись: `whole` пересортировывал `present` заново и затирал
    # порядок «своя карта раньше чужой», выставленный выше. У Нахичеванского
    # соглашения из-за этого чужая карта закона о ратификации (plain, `whole`)
    # обходила собственную карту акта (форма редакций), мера бралась за
    # документ без единиц деления — постановляющую часть закона, — и акт,
    # стоявший в базе с 23 статьями, ПРОПАДАЛ из меры как «единицы деления
    # нет». Собственный документ акта не может уступить первичность чужому:
    # чужие измеряются явной парой аргументов `boundaries.py <src> <clir>`.
    def rank(path: Path) -> tuple[bool, bool]:
        return path.parent.name not in own, not whole_scope(path)

    ordered = sorted(present, key=rank)
    return ordered[0] if ordered else (files[0] if files else None)


def source_declaration_path(src_path: Path) -> Path | None:
    """Find the articles map that actually declares ``src_path``.

    Most packages keep the document beside ``articles.json``.  A normalized
    publication may instead be a declared relative path such as
    ``norm/en.txt`` (OECD GloBE).  §33.1 must follow that declaration rather
    than silently treating the nested document as map-less.

    ДВА ОСНОВАНИЯ, А НЕ ОДНО (29.09.2026, kz-goz-236). ``document`` адресует
    документ ОТНОСИТЕЛЬНО КОРНЯ ПАКЕТА — так его читает
    ``verify/ci/gates/sources/check_source_pinning.py`` (``pkg_root(source) / rel``), и
    так объявлены, например, `sources/conscription/ru.txt` и
    `sources/goz-236/ru.txt`.  Прежний разбор склеивал путь с каталогом КАРТЫ
    и для таких актов возвращал None: карта не находилась, `unit` и `excluded`
    не читались, и отменённая статья показывалась SOURCE_ONLY вместо
    EXCLUDED.  Основание прежнее не отменяется (часть актов адресует документ
    от каталога карты), добавляется второе — и оба пробуются, так что ни один
    ранее читавшийся акт не меняет уровень.
    """
    for parent in (src_path.parent, *list(src_path.parents)[1:4]):
        candidate = parent / "articles.json"
        if not candidate.is_file():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        documents = [payload.get("document"), *[
            entry.get("document") for entry in payload.get("editions", [])
        ]]
        for document in documents:
            if not document:
                continue
            for base in (candidate.parent, *list(candidate.parent.parents)[:3]):
                if (base / str(document)).resolve() == src_path.resolve():
                    return candidate
    return None


_ACT_INDEX: dict[str, dict[str, Path]] = {}


def manifest_act(package: Path) -> str | None:
    """`[metadata].act` манифеста, если объявлен (DECISION-0084 §4).

    Читается tomllib-ом, а не резолвером: схема получит поле в фазе 1, а
    сканер обязан понимать его РАНЬШЕ, чтобы переезд каталогов (фаза 2) не
    переименовал ни одного акта. Без поля имя — путь, как и было."""
    manifest = package / "law.toml"
    if not manifest.is_file():
        return None
    try:
        data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    act = (data.get("metadata") or {}).get("act")
    return act if isinstance(act, str) and act else None


def act_index() -> dict[str, Path]:
    """Объявленные имена → каталоги; строится один раз на корень (ворота
    раскладки подменяют ROOT синтетическим деревом)."""
    key = str(ROOT)
    if key not in _ACT_INDEX:
        _ACT_INDEX[key] = {
            act: m.parent for m in (ROOT / "corpus/laws").rglob("law.toml")
            if (act := manifest_act(m.parent)) is not None}
    return _ACT_INDEX[key]


def act_name(package: Path) -> str:
    """Имя акта — `[metadata].act`, если объявлен (DECISION-0084 §4); иначе
    путь от `corpus/laws` с «/»→«-» (§10, DECISION-0033): `constitution/rights`
    → `constitution-rights`, ровно как назван его CLIR
    `kz-constitution-rights.lawir.json`. Обратная операция — `act_dir`."""
    return manifest_act(package) or "-".join(package.relative_to(ROOT / "corpus/laws").parts)


def own_laws(package: Path) -> list[Path]:
    """`*.law` пакета БЕЗ поддеревьев вложенных пакетов: подкаталог с
    собственным `law.toml` — другой акт, и сборка родителя на нём
    останавливается (граница компилятора, T102)."""
    found: list[Path] = []
    for law in sorted(package.rglob("*.law")):
        if not law.is_file():
            continue
        parent, crossed = law.parent, False
        while parent != package:
            if (parent / "law.toml").is_file():
                crossed = True
                break
            parent = parent.parent
        if not crossed:
            found.append(law)
    return found


def premanifest_dirs() -> list[Path]:
    """Каталоги ДОМАНИФЕСТНОЙ формы: исходники либо карта статей есть, а
    `law.toml` нет ни при себе, ни ниже, ни выше.

    Условие «ни ниже» — то единственное, чем каталог-ГРУППА отличается от
    акта. До 29.08.2026 обход шёл `iterdir()` по первому уровню и звал актом
    КАЖДЫЙ его каталог; сгруппируй корпус по юрисдикции — и `corpus/laws/kz/`
    приехал бы в меру отдельным актом с именем `kz`. Отказ молчалив по
    построению: имя есть, файлы под ним находятся, счёт актов не падает."""
    laws = ROOT / "corpus/laws"
    manifests = {m.parent for m in laws.rglob("law.toml")}
    found: list[Path] = []
    for directory in sorted(path for path in laws.rglob("*") if path.is_dir()):
        if any(m == directory or directory in m.parents for m in manifests):
            continue                                  # манифест при себе или ниже
        if any(p in manifests for p in directory.parents):
            continue                                  # внутри чужого пакета
        if any(f in directory.parents for f in found):
            continue                                  # ниже уже найденного акта
        if any(directory.rglob("*.law")) or any(
                directory.glob("sources/**/articles.json")):
            found.append(directory)
    return found


def known_acts() -> list[str]:
    """Акты с закреплёнными байтами в старой либо пакетной раскладке."""
    # Ветки доманифестной формы `corpus/laws/sources/<акт>/` здесь больше нет.
    # Каталог удалён 29.08.2026 — его исчезновение объявлено DECISION-0033 §6
    # критерием завершения миграции корпуса, — и ветка держалась «на случай
    # отката». После группировки корпуса по правопорядкам она стала вредить:
    # имена в ней задавались именем каталога, а настоящие акты зовутся путём,
    # и `known_acts` выдавал 105 имён при 103 актах — фантомы `civil-code` и
    # `constitution`, у которых `act_dir` возвращал None. Мера их пропускала
    # молча, а `act_source("civil-code")` отдавал устаревшую копию текста.
    acts: set[str] = set()
    # Манифестная форма (§10, DECISION-0033): каталог с собственным law.toml —
    # отдельный акт на любой глубине (constitution/rights/).
    acts.update(
        act_name(m.parent)
        for m in (ROOT / "corpus/laws").rglob("law.toml")
        if own_laws(m.parent)
    )
    # Пакеты, до манифестов не доехавшие, — по тому же правилу имени.
    acts.update(act_name(directory) for directory in premanifest_dirs())
    return sorted(acts)


#: Имена закреплённых документов по языкам, в порядке предпочтения. Порядок
#: содержателен только там, где акт закрепил несколько языков одной редакции;
#: у большинства файл ровно один, и порядок ни на что не влияет.
SOURCE_DOCUMENTS = ("ru.txt", "kk.txt", "en.txt", "fr.txt", "ar.txt",
                    "de.txt", "zh.txt", "ja.txt")
#: `ar.txt` добавлен 30.08.2026 вместе с первым арабским актом корпуса
#: (`osm.mejelle`). `zh.txt` — 19.09.2026 вместе с 民法典 (DECISION-0327):
#: без него мера §33.1 отвечала «фаза 0 не выполнена» при закреплённых байтах.
#: `ja.txt` — конвенция `ja_article` (японские акты, «第N条»): та же причина.
#: Список ЕСТЬ РЕЕСТР, и пропуск в нём молчалив вдвойне:
#: карта без своих байтов уступает чужой, а не найдя ни одной, мера
#: отвечает «фаза 0 не выполнена» — то есть акт с закреплённым срезом
#: выглядит незакреплённым.


def act_source(act: str) -> Path | None:
    """Закреплённый документ акта.

    Имя берётся из `articles.json.document`, а не угадывается: у актов с
    несколькими редакциями раскладка `<акт>-<год>-ru.txt` (Конституция), и
    жёсткий `ru.txt` делал такой акт невидимым для меры целиком — молча.

    Карта статей, однако, НЕ является условием закрепления. `articles.json`
    заводится вместе с УЧЁТОМ границ (фаза 5), а байты закрепляются на фазе 0,
    и между этими фазами акт живёт с настоящим источником и без карты. До
    28.08.2026 такой акт был для меры невидим целиком: `act_declaration`
    возвращала None, а единственная оставшаяся ветка искала байты по
    ДОМАНИФЕСТНОМУ пути `corpus/laws/sources/<акт>/`, которого у пакетных
    актов нет вовсе. Мера отвечала «закреплённого ru-документа нет» и молча
    роняла ДВАДЦАТЬ актов корпуса — включая все семь пакетов Конституции,
    персональные данные, закупки и закон о праздниках, из которого выводится
    официальный календарь всей казахстанской регрессии. Отсутствие меры
    читалось как её благополучие — тот же класс отказа, ради которого
    заведены конвенции заголовков.
    """
    declaration = act_declaration(act)
    if declaration is not None:
        payload = json.loads(declaration.read_text(encoding="utf-8"))
        # Форма `{"editions": [...]}` (DECISION-0026): у акта с несколькими
        # закреплёнными редакциями в одном каталоге учёт ведётся по каждой.
        # Мера считает статьи ОДНОГО текста, поэтому здесь берётся первая
        # объявленная редакция — она же основная для отчёта; остальные
        # измеряются явной парой аргументов `boundaries.py <src> <clir>`.
        # Без этой ветки акт становился невидим целиком: `document` у него
        # нет, и мера отвечала «фаза 0 не выполнена» при закреплённых байтах.
        names = [payload["document"]] if payload.get("document") else [
            e.get("document") for e in payload.get("editions", []) if e.get("document")
        ]
        for name in names:
            if name and (declaration.parent / name).is_file():
                return declaration.parent / name
        fallback = declaration.parent / "ru.txt"
        if fallback.is_file():
            return fallback
    # Пакетная раскладка без карты статей: байты лежат в
    # `corpus/laws/<акт>/sources/<...>/<язык>.txt`. Выбор детерминирован
    # (`sorted`) и НЕ молчалив: разрешённый путь печатается первой строкой
    # отчёта, поэтому у акта с несколькими закреплёнными редакциями в одном
    # каталоге видно, какая измерена, — а измерить остальные можно явной
    # парой аргументов `boundaries.py <src> <clir>`, как и раньше.
    # Каталог берётся `act_dir`, а не склейкой `corpus/laws/<акт>`: у акта на
    # втором и глубже уровне склейка даёт несуществующий путь, ветка целиком
    # пропускается, и `act_source` возвращает None — то есть «фаза 0 не
    # выполнена» при закреплённых байтах. Задевало только акты БЕЗ
    # `articles.json` (у остальных источник находит `act_declaration` выше), и
    # потому пряталось: на репетиции переезда 29.08.2026 из 90 переехавших
    # актов меру потеряли ровно пять — те, у кого фаза 0 сделана, а фаза 5 нет.
    package = act_dir(act)
    if package is not None and package.is_dir():
        # Каталог закреплённых байтов зовётся ПРОСТЫМ именем акта
        # (`sources/budget/`), а сам акт при вложенности — путём
        # (`kz-budget-2026`). Своим считается источник под любым из двух.
        own_names = {act, package.name}
        for name in SOURCE_DOCUMENTS:
            found = sorted(package.glob(f"sources/**/{name}"))
            if not found:
                continue
            # У пакета может быть НЕСКОЛЬКО закреплённых документов: акт плюс
            # то, на что он ссылается несущим образом (мирные собрания держат
            # ещё и НП КС 61-НП). Алфавитный `found[0]` брал чужой документ, и
            # акт выпадал из меры молча — у постановления нет заголовков
            # «Статья N», мера возвращала ноль строк, а ноль строк читается как
            # «мера неприменима». Собственный источник акта — тот, чей каталог
            # назван его именем; остальные измеряются явной парой аргументов.
            own = [path for path in found if path.parent.name in own_names]
            return own[0] if own else found[0]
    # Доманифестный хвост `corpus/laws/sources/<акт>/<язык>.txt` удалён вместе
    # с каталогом (29.08.2026). Перебор SOURCE_DOCUMENTS остался выше, в
    # пакетной ветке: язык закреплённого документа не обязан быть русским —
    # корпус хранит и казахские редакции, и жёсткий `ru.txt` делал такой акт
    # невидимым целиком.
    return None


NAMESPACE_RE = re.compile(r'^\s*namespace\s+"([^"]+)"', re.M)


def clir_root() -> Path:
    """Каталог CLIR, который читает мера: снимок изолированного профиля, если
    он выбран переменной `LAW_WORK_PROFILE_STATE`, иначе общий `corpus/clir`."""
    try:
        import work_profile  # corpus/lib — путь добавлен выше.
    except ImportError:  # pragma: no cover — скилл без дерева корпуса.
        return ROOT / "corpus" / "clir"
    return Path(work_profile.clir_directory())


def clir_by_namespace() -> dict[str, Path]:
    """namespace → CLIR. Имена файлов CLIR не совпадают с именами актов
    (`marriage-conditions.law` → `kz-marriage.lawir.json`), поэтому индекс
    строится по namespace — тем же способом, что `verify/ci/gates/sources/check_source_pinning.py`.
    Вторая копия соглашения об именовании здесь и была бы дефектом.

    ИЗОЛИРОВАННЫЙ ПРОФИЛЬ ЧИТАЕТ СВОЙ СНИМОК (29.09.2026). Каталог берётся из
    `corpus/lib/work_profile.py`, который переключается переменной
    `LAW_WORK_PROFILE_STATE`; раньше путь был вшит как `corpus/clir`, и в
    изолированном прогоне мера глубины и срез мёртвых символов аудита смотрели
    на общий снимок — то есть на ПРЕЖНУЮ версию изменённых пакетов. Измерено
    на `kz-goz-236`: статьи 5–9 и 21, выраженные нормами, показывались
    SOURCE_ONLY, а восемь позиций состава, только что ставшие живыми, —
    мёртвыми. Без переменной окружения поведение прежнее: общий снимок.
    """
    directory = clir_root()
    index: dict[str, Path] = {}
    for path in sorted(directory.glob("*.lawir.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        namespace = (doc.get("package") or {}).get("namespace")
        if namespace:
            index[namespace] = path
    return index


def act_dir(act: str) -> Path | None:
    """Каталог акта: имя с «-» разворачивается обратно в путь по границам
    существующих каталогов — операция, обратная `act_name`.

    Разбор рекурсивный и с возвратом, а не в один разрез: `constitution-rights`
    лежит на двух уровнях, но при группировке корпуса по юрисдикции тот же акт
    зовётся `kz-constitution-rights` и лежит на трёх, а `kz-civil-code-terms` —
    на двух, хотя дефисов в нём столько же. Один разрез (версия до 29.08.2026)
    брал только двухуровневый случай и возвращал None на любом более глубоком:
    акт молча выпадал и из меры §33.1, и из `act_laws`."""
    declared = act_index().get(act)
    if declared is not None:
        return declared
    plain = ROOT / "corpus" / "laws" / act
    if plain.is_dir() and manifest_act(plain) in (None, act):
        return plain

    def leaf(candidate: Path) -> bool:
        """Конец пути — корень пакета (чьё манифестное имя не спорит с
        искомым) либо каталог доманифестной формы."""
        if (candidate / "law.toml").is_file():
            return manifest_act(candidate) in (None, act)
        return not any(candidate.rglob("law.toml"))

    def walk(base: Path, rest: list[str]) -> Path | None:
        if not rest:
            return base if leaf(base) else None
        for cut in range(1, len(rest) + 1):
            candidate = base / "-".join(rest[:cut])
            if not candidate.is_dir():
                continue
            hit = walk(candidate, rest[cut:])
            if hit is not None:
                return hit
        return None

    return walk(ROOT / "corpus" / "laws", act.split("-"))


def act_laws(act: str) -> list[Path]:
    """Все исходники одиночного либо многофайлового акта.

    Для каталога — без поддеревьев вложенных пакетов: подкаталог с
    собственным law.toml — другой акт (граница сборки компилятора, T102)."""
    package = act_dir(act)
    if package is not None:
        return own_laws(package)
    return sorted(p for p in ROOT.glob(f"corpus/laws/{act}*.law")
                  if p.stem == act or p.stem.startswith(f"{act}-"))


def satellite_packages(package: Path) -> list[Path]:
    """Вложенные пакеты акта, у которых НЕТ собственного закреплённого текста.

    §10 / DECISION-0033 кладёт семью пакетов ДЕРЕВОМ: `constitution/rights/`
    несёт свой `law.toml`, и для компилятора это отдельная единица сборки
    (T102) — `own_laws` останавливается на ней правильно. Для меры §33.1 то же
    дерево читается иначе: спутник не закрепляет ни байтов, ни карты статей, он
    формализует статьи РОДИТЕЛЬСКОГО текста. Измерить его отдельно нельзя по
    построению — `act_source` отдаёт None, и `measure_act` такой акт молча
    пропускает; не войди его CLIR в измерение родителя, семантика семьи для
    меры не существует вовсе.

    Цена молчания измерена 02.09.2026 на Конституции РК — единственной семье
    такой формы в корпусе. `act_clirs` находила один пакет из девяти, и
    корпусный храповик держал по акту EXECUTABLE 5 / UNEXPLAINED 86 при
    настоящих 86 / 0: 81 статья, выводящая право, числилась «текст сохранён и
    только». Ошибка была в БЕЗОПАСНУЮ сторону и потому не краснела ничем.

    Спутник со СВОИМ источником сюда не попадает: он измеряется сам, и войди
    он ещё и в родителя — те же статьи считались бы дважды.
    """
    out: list[Path] = []
    for manifest in sorted(package.rglob("law.toml")):
        nested = manifest.parent
        if nested == package or not own_laws(nested):
            continue
        if act_source(act_name(nested)) is not None:
            continue
        out.append(nested)
    return out


def act_clirs(act: str, *, index: dict[str, Path] | None = None) -> list[Path]:
    """ВСЕ CLIR-пакеты акта, разрешённые через namespace его исходников.

    Прежняя версия брала `clirs[0]` из glob по имени файла: у Конституции из
    восьми пакетов мерился один, а `marriage-conditions` не находился вовсе.
    Побочно исчезает audit-world `kz-constitution-linked` — у него нет своего
    `.law`, он повторяет узлы семи пакетов. Дедупликация по id в `depth`
    оставлена страховкой на случай, если такой пакет всё же попадёт в список.

    Вложенные пакеты-спутники добираются `satellite_packages`: у акта-дерева
    исходники родителя называют лишь его собственный namespace, и одного
    `act_laws` мало (см. там же).

    Явный индекс позволяет адресным воротам повторно использовать уже
    отобранные снимки, включая namespace спутников. Без него выбор каталога
    изолированного профиля и полный индекс остаются прежними.
    """
    if index is None:
        index = clir_by_namespace()
    out: list[Path] = []
    laws = list(act_laws(act))
    package = act_dir(act)
    if package is not None:
        for satellite in satellite_packages(package):
            laws.extend(own_laws(satellite))
    for law in laws:
        match = NAMESPACE_RE.search(law.read_text(encoding="utf-8"))
        if match and match.group(1) in index:
            path = index[match.group(1)]
            if path not in out:
                out.append(path)
    return sorted(out)


def resolve_paths(args: list[str]) -> tuple[Path, list[Path]]:
    if len(args) == 2:
        return Path(args[0]).resolve(), [Path(args[1]).resolve()]
    act = args[0]
    src = act_source(act)
    clirs = act_clirs(act)
    if src is None:
        sys.exit(f"нет закреплённых байтов акта {act}: искали "
                 f"corpus/laws/<группа>/{act}/sources/**/"
                 f"{{{','.join(SOURCE_DOCUMENTS)}}} — фаза 0 не выполнена")
    if not clirs:
        sys.exit(f"нет corpus/clir/kz-{act}*.lawir.json — акт не лоуверен")
    return src, clirs


def _edition_probe_time(edition: dict) -> str | None:
    """Момент, заведомо лежащий внутри применимости редакции: старт её
    главного `in_force`/`restored` события (либо конец, если начало открыто
    в бесконечность). Не даёт применимость сам — только зонд для
    `is_applicable`, чтобы спросить: применима ли РЯДОМ СТОЯЩАЯ редакция того
    же work в этот же момент."""
    for event in edition.get("lifecycle", []) or []:
        if event.get("status") not in ("in_force", "restored"):
            continue
        extent = event.get("extent")
        if isinstance(extent, dict):
            start = extent.get("start")
            if start not in (None, "-infinity"):
                return str(start)
            end = extent.get("end")
            if end not in (None, "infinity"):
                return str(end)
            continue
        if extent is not None:
            return str(extent)
    return None


def _editions_share_period(measured: dict, candidate: dict) -> bool:
    """Та же редакция либо редакция того же work, чей период применимости
    пересекается с измеряемым.

    Группировка по одному `work` (ниже) была заведена ради языковых
    вариантов ОДНОЙ редакции: у Конституции ru- и kk-текст редакции 1995
    имеют идентичный lifecycle, и правило, заякоренное в оба сразу, обязано
    засчитаться один раз, а не потеряться (найдено 27.08.2026: 85 → 86
    ложно). Но `work` — это ось «один и тот же акт», а не «один и тот же
    период»: у russkaya-pravda ОДИН source (RUSSKAYA_PRAVDA) держит ДВЕ
    временные редакции — Краткую (in_force 1072–1113) и Пространную
    (in_force с 1113) — со сквозной нумерацией `article/N` в обеих. Голая
    проверка `work` засчитывала статью 18 Краткой (тариф виры «тиун княж»)
    как формализующую статью 18 Пространной (персты — другое содержание
    целиком), потому что обе редакции — один work (найдено 29.08.2026:
    ложные EXECUTABLE на статьях без единого своего правила).
    Различитель — применимость (машина D1, §31), а не только `work`:
    редакции одного work группируются, только если их периоды
    ПЕРЕСЕКАЮТСЯ. У Конституции периоды идентичны — пересекаются
    тривиально. У Краткой/Пространной периоды СМЕЖНЫЕ, но не пересекаются
    (конец Краткой исключён, начало Пространной в ту же дату включено) —
    `is_applicable` в обе стороны даёт False, группировка не срабатывает.
    Используется готовая машина `lawref.editions.applicability.is_applicable` (та же,
    что `edition_projection` в `engines/lawref/lawref/analysis/impact.py`), а не собственная
    копия интервальной арифметики."""
    if candidate.get("id") == measured.get("id"):
        return True
    candidate_probe = _edition_probe_time(candidate)
    if candidate_probe is not None and is_applicable(measured, candidate_probe):
        return True
    measured_probe = _edition_probe_time(measured)
    if measured_probe is not None and is_applicable(candidate, measured_probe):
        return True
    return False


def depth(src_path: Path, clir_paths: Path | list[Path], *,
          source_unit: str | None = None) -> dict:
    if isinstance(clir_paths, Path):
        clir_paths = [clir_paths]
    text = src_path.read_text(encoding="utf-8")
    # Узлы всех пакетов акта в одном множестве, дедупликация по id: пакет
    # разрезан по разделам закона, а статья принадлежит акту, не пакету.
    nodes: dict[str, dict] = {}
    for path in clir_paths:
        for node in json.loads(path.read_text(encoding="utf-8")).get("nodes", []):
            nodes.setdefault(str(node.get("id", "")), node)
    doc = {"nodes": list(nodes.values())}
    # Объявленная единица деления лежит рядом с закреплёнными байтами — там
    # же, где её читает `verify/ci/gates/sources/check_source_pinning.py`. Сигнатура `depth` не
    # меняется: путь к карте выводится из пути источника, а не передаётся
    # вторым способом, который разошёлся бы с первым.
    unit = None
    declaration: dict = {}
    declaration_path = source_declaration_path(src_path)
    if declaration_path is not None:
        payload = json.loads(declaration_path.read_text(encoding="utf-8"))
        # Форма `{"editions": [...]}`: единица объявляется у КАЖДОЙ редакции,
        # и брать её надо у той, чей документ сейчас меряется. Прежде читался
        # только верхний уровень, и у акта в этой форме объявленная единица
        # была для меры глубины НЕВИДИМА — мера молча уходила в
        # автоопределение. Обходили это дублированием `unit` наверху
        # (`decalogue`, `russkaya-pravda`); у `alash-orda` дубля нет, и его
        # `section` не читался ни разу. Учёт статей
        # (`verify/ci/gates/sources/check_source_pinning.py`) редакцию находил всегда — две меры
        # §33.1 читали РАЗНЫЕ единицы одного акта.
        declaration = payload
        for entry in payload.get("editions", []):
            if Path(str(entry.get("document", ""))).name == src_path.name:
                declaration = entry
                break
        unit = declaration.get("unit") or payload.get("unit")
    # Объявленная единица нужна ДВАЖДЫ и в разном виде: ниже `unit`
    # переписывается человеческим именем для отчёта («параграф», «статья»), а
    # разбору локаторов нужно само имя конвенции — по нему `locator_unit`
    # решает, параграф здесь единица деления или адрес внутри статьи.
    if source_unit is not None:
        if source_unit not in CNXML_UNITS | {OPENSTAX_SECTION_UNIT}:
            raise ValueError(f"unsupported explicit source unit: {source_unit}")
        if unit is not None and unit != source_unit:
            raise ValueError("explicit source unit conflicts with source declaration")
        unit = source_unit
    elif unit is None and src_path.suffix == ".cnxml":
        unit = "cnxml_module"
    declared_unit = unit
    cnxml_elements = ({m.group(1) for m in article_matches(text, "cnxml_element")}
                      if declared_unit in CNXML_UNITS else None)
    excluded = {str(number) for number in declaration.get("excluded", [])}
    # Номер НОРМАЛИЗУЕТСЯ: у пары конвенций OCR разрывает цифры пробелами
    # («§ 6 4 .» в издании Сыздық), и сырой захват дал бы единицу «6 4 »,
    # которую locator `article/64` не находит НИКОГДА. Симметрию держит
    # `number=` у ArticleConvention в verify/ci/gates/sources/check_source_pinning.py:
    # там нормализатор есть с 01.09.2026, здесь его не было — и мера теряла
    # ровно одну единицу из 129 молча, показывая EXECUTABLE 27 при 28
    # выраженных.
    articles = [("".join(m.group(1).split()), m.group(2).strip())
                for m in article_matches(text, unit, declaration)]
    # Имя единицы для отчёта: акт, поделённый на слова, обязан и называться
    # словами. «Статей: 45» у «Қара сөз» было бы не опечаткой отчёта, а
    # утверждением о структуре произведения, которого в нём нет.
    exact_publication = declared_unit in CNXML_UNITS | {OPENSTAX_SECTION_UNIT}
    unit = {"openstax_section": "раздел OpenStax",
            "cnxml_module": "модуль CNXML", "cnxml_element": "элемент CNXML",
            "word": "слово", "clause": "пункт", "oked_code": "код",
            "point_in_section": "пункт",
            "point_paren": "пункт",
            # Пункт акта, чью нумерацию правила поправки («7-1» рядом с «7»).
            # Имя стои́т здесь, а не выводится из имени конвенции: без строки
            # отчёт печатает «статей: N» о документе, который на статьи не
            # делится, и число при этом верно — неверно слово.
            "point_amended": "пункт",
            # Приказ, который делит себя ПРИЛОЖЕНИЯМИ (№ 695: тридцать
            # приложений, у каждого свои главы и своя нумерация пунктов).
            # «Статей: 30» о нём было бы утверждением о структуре, которой
            # у него нет: собственных статей у приказа ноль.
            "prilozhenie": "приложение",
            "la_paragraph": "пункт",
            "inst_paragraph": "параграф",
            "posylka": "посылка",
            "kefalaio": "глава",
            # Единица «Начал» Евклида: акт, поделённый на предложения,
            # обязан и называться предложениями. «Статей: 6» о книге
            # Евклида было бы утверждением о структуре сочинения,
            # которого в нём нет.
            "protasis": "предложение",
            # Определение «Начал» — своя единица и своё имя: «статей: 1» о
            # разделе Ὅροι было бы тем же утверждением о несуществующей
            # структуре, что и «статей» о предложениях.
            "horos": "определение",
            # Единица «Disquisitiones arithmeticae» — артикул: Гаусс
            # адресует себя «art. 45», и «статей: 6» о разделе его книги
            # было бы утверждением о структуре, которой у неё нет.
            "articulus": "артикул",
            # Единица трактата Пачоли (перевод Гейсбека 1914) — глава:
            # «статей: 36» о трактате было бы утверждением о структуре,
            # которой у него нет.
            "en_chapter": "глава",
            "digest_lex": "лекс",
            "canon": "канон",
            "yar_rule": "правило",
            "principle": "принцип",
            "numbered_section": "секция",
            "policy_section": "раздел политики",
            "marginal": "заметка",
            # Листок-вкладыш делится ИМЕНОВАННЫМИ разделами; «статей: 26» о
            # документе без единой статьи было бы утверждением о его
            # структуре, которого он не делает.
            "ru_named_section": "раздел",
            "turn": "оборот",
            "verse": "стих",
            "talmud_segment": "сегмент",
            # Немецкий закон делится параграфами, и «статей: 139» о
            # BVerfGG было бы утверждением о структуре, которой у него
            # нет: § — не сокращение слова «статья», а своя единица.
            "de_paragraph": "параграф",
            # МСФО делится нумерованными параграфами, и «статей: 103» о
            # стандарте было бы утверждением о структуре, которой у него нет:
            # статьи есть у самого регламента (их три), а сто три параграфа —
            # у стандарта, который регламент вводит приложением.
            "ifrs_paragraph": "параграф",
            "ias2008_paragraph": "параграф",
            "line": "стих"}.get(unit, "статья")
    if not articles:
        # Разделов нумерация римская, а locator-ы фрагментов арабские
        # (`section/1`): единица одна, запись разная — сводим к номеру.
        articles = [(str(roman_to_int(m.group(1))), m.group(2).strip())
                    for m in SECTION_RE.finditer(text)]
        if articles:
            unit = "раздел"
    seen, ordered = set(), []
    for num, title in articles:
        if num not in seen:
            seen.add(num)
            ordered.append((num, title))

    # Разрешение якоря в номер статьи — ДВА пути, и первый предпочтителен:
    # якорь-StableId ведёт к узлу-фрагменту, у фрагмента есть locator, из
    # locator-а берётся номер. Соглашение об именовании при этом не нужно
    # вовсе. Второй путь — строка внешнего реестра (`…ART-26-1`): им корпус
    # ссылался раньше, и пока такие ссылки есть, мера от соглашения зависит.
    # Редакции ИЗМЕРЯЕМОГО документа. Мера считает статьи одного текста, и
    # якорь в другую редакцию того же акта к нему отношения не имеет: у
    # Конституции статья 3 редакции 1995 и статья 3 редакции 2026 — разные
    # положения. Без фильтра правило про 1995 засчитывалось статье 2026 и
    # молча поднимало EXECUTABLE (найдено 27.08.2026: 85 → 86 ложно).
    # Редакция выводится из данных, а не из соглашения об именах:
    # publication.local_path указывает на измеряемый файл, у публикации есть
    # edition, у редакции — work; принимаются редакции этого work, чей период
    # применимости пересекается с измеряемой (правило заякорено сразу в ru- и
    # kk-фрагменты ОДНОЙ статьи — периоды идентичны, пересекаются тривиально).
    # Голого совпадения work мало: у russkaya-pravda один work держит две
    # временные редакции с несовпадающими периодами и сквозной нумерацией
    # `article/N` — без пересечения периодов Краткая утекала бы в измерение
    # Пространной (см. `_editions_share_period`).
    # Какая публикация — измеряемый файл, определяется СВЕРКОЙ БАЙТОВ, а не
    # именем: `local_path` до CLIR не доезжает (теряется при lowering), а
    # соглашение об именах файлов — ровно та догадка, которой мера избегает.
    # `documentHash` §27.3 закрепляет те же байты, что лежат на диске.
    measured_editions: set[str] = set()
    editions_by_id = {str(n.get("id", "")): n for n in doc.get("nodes", [])
                      if n.get("kind") == "source_edition"}
    digest = "sha256:" + hashlib.sha256(src_path.read_bytes()).hexdigest()
    for node in doc.get("nodes", []):
        if node.get("kind") != "publication":
            continue
        if str(node.get("documentHash", "")) != digest:
            continue
        edition = editions_by_id.get(str(node.get("edition", "")))
        work = edition.get("work") if edition else None
        if exact_publication and (edition is None or not work):
            raise ValueError("pinned publication has an unresolved edition or work")
        for candidate_id, candidate in editions_by_id.items():
            if work is None:
                # Редакция публикации не разрешилась: фильтр не может
                # отличить свою/чужую по данным, которых нет, и остаётся
                # открытым — как до всего фильтра целиком.
                measured_editions.add(candidate_id)
            elif exact_publication:
                # XML ids are intrinsic to these exact bytes. A different
                # publication of the same work cannot lend its element anchors,
                # even if the edition periods overlap.
                if candidate_id == str(node.get("edition", "")):
                    measured_editions.add(candidate_id)
            elif (candidate.get("work") == work
                  and _editions_share_period(edition, candidate)):
                measured_editions.add(candidate_id)

    if exact_publication and not measured_editions:
        raise ValueError("source hash is not pinned by an own CLIR publication")

    fragments: set[str] = set()
    by_id: dict[str, tuple[str, ...]] = {}
    foreign_fragments: set[str] = set()
    for node in doc.get("nodes", []):
        if node.get("kind") != "fragment":
            continue
        node_id = str(node.get("id", ""))
        if measured_editions and str(node.get("edition", "")) not in measured_editions:
            foreign_fragments.add(node_id)
            continue
        # Единицу называет ПЕРВЫЙ адрес локатора, и разбор живёт рядом с самим
        # выражением (`locator_unit` в corpus/tools/lib/act_split.py). Прежде
        # здесь собирались номера по ВСЕМ совпадениям, и `article/63/paragraph/3`
        # объявлял вдобавок несуществующую «статью 3» — знаменатель рос ложными
        # единицами SOURCE_ONLY/UNEXPLAINED, из которых пакет не режет ничего.
        locator = str(node.get("locator", ""))
        if cnxml_elements is not None:
            element = locator_units(locator, "cnxml_element")
            if not element or element[0] not in cnxml_elements:
                raise ValueError(f"fragment does not resolve in pinned CNXML: {node_id}")
        found = locator_units(locator, declared_unit,
                              declaration.get("locator"))
        if declared_unit == OPENSTAX_SECTION_UNIT and (not found or found[0] not in seen):
            raise ValueError(f"fragment does not resolve in pinned OpenStax sections: {node_id}")
        if found:
            fragments.update(found)
            # Один фрагмент диапазона (`rules/9-14`) адресует КАЖДУЮ
            # измеряемую единицу. Хранить склеенную строку здесь нельзя:
            # правило с таким якорем затем искало бы фиктивный номер
            # "9, 10, …, 14" и шесть действительно исполнимых пунктов
            # становились SOURCE_ONLY.
            by_id[node_id] = found

    deriving: dict[str, int] = {}
    interpreted: dict[str, int] = {}
    anchoring: dict[str, int] = {}
    # Поражаемые правила считаются ОТДЕЛЬНОЙ осью, а не уровнем: уровень §33.1
    # отвечает «выводится ли», а леджер предложений (DECISION-0067) спрашивает
    # «выводится ли ПОРАЖАЕМО» — маркер презумпции в тексте гасится только
    # правилом defeasible-слоя. Ось живёт здесь, а не в леджере, чтобы
    # разрешение якорей (фильтр редакций, locator, гейт толкования) не имело
    # второй копии.
    defeasible: dict[str, int] = {}
    gated_nodes = interpretation_gated(doc.get("nodes", []))
    unresolved = 0
    other_edition = 0
    position_ids = {
        str(node.get("id", ""))
        for node in doc.get("nodes", [])
        if is_position_node(node)
    }
    position_template_ids = {
        node_id.replace("#Position", "#", 1)
        for node_id in position_ids
    }
    for node in doc.get("nodes", []):
        kind = node.get("kind", "")
        if is_position_node(node) or (
            kind == "norm_template"
            and str(node.get("id", "")) in position_template_ids
        ):
            continue
        for anchor in node.get("anchors", []) or []:
            key = str(anchor)
            if key in foreign_fragments:
                # Якорь разрешился во фрагмент ЧУЖОЙ редакции: он не
                # неразрешённый (адрес верен) и не наш — считается отдельно.
                other_edition += 1
                continue
            nums = by_id.get(key)
            if nums is None:
                match = (None if exact_publication
                         else ANCHOR_ARTICLE_RE.search(key))
                # В StableId составной номер записывается как `95_1`, в
                # заголовке и locator-е источника — как `95-1`. Нормализация
                # применяется только после выделения номера статьи, поэтому
                # не изменяет суффиксы языка и пункта якоря.
                nums = (match.group(1).replace("_", "-"),) if match else None
            if nums is None:
                unresolved += 1
                continue
            for num in nums:
                anchoring[num] = anchoring.get(num, 0) + 1
                if kind in DERIVING_KINDS:
                    if node.get("strength") == "defeasible":
                        defeasible[num] = defeasible.get(num, 0) + 1
                    if str(node.get("id", "")) in gated_nodes:
                        interpreted[num] = interpreted.get(num, 0) + 1
                    else:
                        deriving[num] = deriving.get(num, 0) + 1

    rows = []
    for num, title in ordered:
        # Отмененная или еще не вступившая в силу статья остается в
        # закрепленном документе и должна быть адресуемой, но не может
        # выглядеть как «пробел формализации» активной редакции. Если на нее
        # все-таки есть правило, это не маскируем: такая статья EXECUTABLE и
        # требует отдельной проверки временной применимости.
        if num in excluded and not deriving.get(num) and not interpreted.get(num):
            level = "EXCLUDED"
        elif deriving.get(num):
            level = "EXECUTABLE"
        elif interpreted.get(num):
            # Вывод есть, но только при ВЫБРАННОМ прочтении §152. Отдельный
            # уровень, а не `EXECUTABLE`: на обычном деле правила нет вовсе.
            # И не `ANCHORED`: адресуемость тут ни при чём — норма написана и
            # исполнима, она лишь не входит в базовую теорию.
            level = "INTERPRETED"
        elif anchoring.get(num):
            level = "ANCHORED"
        elif num in fragments:
            level = "SOURCE_ONLY"
        else:
            level = "—"
        rows.append({"article": num, "title": title, "level": level,
                     "deriving": deriving.get(num, 0),
                     "interpreted": interpreted.get(num, 0),
                     "anchoring": anchoring.get(num, 0),
                     "defeasible": defeasible.get(num, 0)})
    return {"source": src_path, "clir": clir_paths, "rows": rows,
            "unresolved": unresolved, "otherEdition": other_edition,
            "unit": unit, "excludedArticles": excluded}


def non_normative(act: str, used: list[Path]) -> list[Path]:
    """CLIR-файлы, похожие на пакеты акта по имени, но не разрешённые через
    namespace его исходников: у них нет собственного `.law`.

    Такой пакет — не нормативный, а порождённый инструментом (audit-world
    `kz-constitution-linked` объединяет узлы семи пакетов и добавляет
    фикстуры divergence). Мера полноты акта обязана считаться по нормативным
    пакетам: иначе тестовая оснастка засчитывается как формализация —
    у Конституции ровно так и выходило со ст. 19."""
    used_set = set(used)
    return [p for p in sorted(ROOT.glob(f"corpus/clir/kz-{act}*.lawir.json"))
            if p not in used_set]


def _clir_line(paths: list[Path]) -> str:
    # A private work-profile intentionally writes CLIR outside the repository.
    # The measurement accepts that explicit path; rendering must not turn a
    # successful measure into an exception merely because it cannot be shown
    # relative to ROOT.
    names = []
    for path in paths:
        try:
            names.append(str(path.relative_to(ROOT)))
        except ValueError:
            names.append(str(path))
    if len(names) == 1:
        return names[0]
    return f"{len(names)} пакетов — " + ", ".join(Path(n).name for n in names)


def render(result: dict) -> None:
    rows = result["rows"]
    if not rows:
        # Нули читаются как измерение. Акт без заголовков «Статья N» (Правила
        # структурированы пунктами) — это НЕприменимость меры, а не нулевое
        # покрытие, и сказать надо именно это.
        print(f"Источник: {result['source'].relative_to(ROOT)} — "
              "заголовков «Статья N» нет: мера по статьям неприменима")
        print(f"CLIR: {_clir_line(result['clir'])}")
        if result["unresolved"]:
            print(f"  якорей в пакете: {result['unresolved']}, ни один не разрешён "
                  "в номер статьи — для этого акта нужна своя единица деления "
                  "(пункт/раздел), она не заведена")
        print("  байтовую долю смотрите в verify/ci/gates/sources/check_source_pinning.py")
        return
    counts = {"EXECUTABLE": 0, "INTERPRETED": 0, "ANCHORED": 0, "SOURCE_ONLY": 0,
              "EXCLUDED": 0, "—": 0}
    for row in rows:
        counts[row["level"]] += 1
    total = len(rows)
    unit = result.get("unit", "статья")
    plural = {"статья": "статей", "слово": "слов", "пункт": "пунктов",
              "посылка": "посылок",
              "глава": "глав",
              "предложение": "предложений", "определение": "определений",
              "принцип": "принципов", "секция": "секций",
              "заметка": "заметок", "стих": "стихов",
              "лекс": "лексов", "правило": "правил",
              "канон": "канонов", "оборот": "оборотов",
              "раздел": "разделов",
              "сегмент": "сегментов",
              "параграф": "параграфов",
              "приложение": "приложений"}.get(unit, "разделов")
    print(f"Источник: {result['source'].relative_to(ROOT)} — {plural}: {total}")
    print(f"CLIR: {_clir_line(result['clir'])}")
    print(f"  EXECUTABLE  {counts['EXECUTABLE']:>3}  из единицы ВЫВОДИТСЯ (есть правило)")
    print(f"  INTERPRETED {counts['INTERPRETED']:>3}  выводится ТОЛЬКО при выбранном прочтении §152")
    print(f"  ANCHORED    {counts['ANCHORED']:>3}  адресуема (факты/closure), вывода нет")
    print(f"  SOURCE_ONLY {counts['SOURCE_ONLY']:>3}  только текст фрагмента")
    print(f"  EXCLUDED    {counts['EXCLUDED']:>3}  отменена или не вступила в силу в измеряемой редакции")
    print(f"  вне пакета  {counts['—']:>3}")
    for path in result.get("excluded") or []:
        print(f"  вне меры: {path.name} — не нормативный пакет (нет своего .law)")
    if result["unresolved"]:
        print(f"  якорей, не разрешённых в статью: {result['unresolved']} "
              "(§33 ожидает StableId фрагмента; корпус ссылается строками "
              "внешнего реестра — мера зависит от соглашения об именовании)")
    # Объявленный `scope` учёта §33.1 — часть акта, которую пакет БЕРЁТСЯ
    # покрывать. Без него всякая единица вне охвата попадала в «кандидаты на
    # формализацию»: у Цицерона это дало бы 65 строк диалога как недоделку,
    # тогда как §§1–18 и §§23–69 — рассуждение, а не нормы, и это объявлено.
    # Список читается рядом с документом; ЧИСЛО вне охвата печатается всегда,
    # чтобы охват нельзя было сузить незаметно.
    scope = None
    declared: set[str] = set()
    declaration = result["source"].parent / "articles.json"
    if declaration.is_file():
        payload = json.loads(declaration.read_text(encoding="utf-8"))
        # Форма `{"editions": [...]}`: охват принадлежит РЕДАКЦИИ, а не акту.
        # `depth()` выше её читает с самого начала, а этот раздел читал только
        # верхний уровень — и у многоредакционного акта охват молча оказывался
        # НЕ ОБЪЯВЛЕННЫМ: все единицы вне охвата печатались «кандидатами на
        # формализацию». Цена измерена на «Антигоне»: 1173 стиха хора и плача
        # выдавались за недоделку при полностью покрытом охвате из 79.
        # Редакция выбирается по имени измеряемого документа — тем же
        # соглашением, что в `depth()`; две копии соглашения разошлись бы.
        entry = payload
        for candidate in payload.get("editions", []):
            if Path(str(candidate.get("document", ""))).name == result["source"].name:
                entry = candidate
                break
        raw = entry.get("scope")
        if isinstance(raw, list):
            scope = {str(a) for a in raw}
        declared = {str(a) for a in (entry.get("declared") or {})}
    weak = [r for r in rows if r["level"] in ("SOURCE_ONLY", "—")]
    if scope is not None:
        outside = [r for r in weak if r["article"] not in scope]
        weak = [r for r in weak if r["article"] in scope]
        if outside:
            print(f"  вне объявленного охвата: {len(outside)} "
                  f"(scope в {declaration.relative_to(ROOT)})")
    # Статья, объявленная границей С ПРИЧИНОЙ, — сделанная работа, а не
    # кандидат в неё. До 28.08.2026 инструмент читал у карты только `scope`, и
    # такая статья по-прежнему стояла в списке «кандидаты на формализацию»:
    # совет сделать сделанное, из-за которого честно объявленная граница
    # выглядела недоделкой. Число печатается ВСЕГДА — по той же причине, по
    # которой печатается число вне охвата: границу нельзя объявить незаметно.
    # Правдивость самих причин проверяет `verify/ci/gates/sources/check_source_pinning.py` по тексту
    # статьи; здесь они только не выдаются за пробел.
    if declared:
        named = [r for r in weak if r["article"] in declared]
        weak = [r for r in weak if r["article"] not in declared]
        print(f"  объявлены границей с причиной: {len(named)}"
              + (f" ({', '.join(r['article'] for r in named)})" if named else "")
              + f" — причины в {declaration.relative_to(ROOT)},"
              " проверяются по тексту статьи воротами закрепления")
    if weak:
        print("\nБез единой нормы — кандидаты либо на формализацию, либо в объявленные")
        print("границы `sources/<акт>/articles.json` с указанием, ЧЕГО в статье нет:")
        for row in weak:
            print(f"  {unit.capitalize()} {row['article']}. {row['title']}")
    shallow = [r for r in rows if r["level"] == "ANCHORED"]
    if shallow:
        print(f"\nАдресуемы, но ничего не выводят ({len(shallow)}): "
              + ", ".join(r["article"] for r in shallow))
        print("Это не дефект: в статье об аудите фонда нет ставки. Но и «формализовано»")
        print("про них означает не то же, что про статью со ставкой, — и разница видна.")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "--all":
        # Обход по каталогам источников, а не по `*/ru.txt`: акт с
        # многоредакционной раскладкой не имеет файла с таким именем и раньше
        # выпадал из `--all` без единой строки о себе.
        acts = known_acts()
        if not acts:
            print("нет актов с закреплённым источником")
            return 0
        first = True
        for act in acts:
            src = act_source(act)
            clirs = act_clirs(act)
            if not act_laws(act):
                print(f"{act}: каталог текстов без собственного акта — "
                      "тексты используются другим пакетом\n")
                continue
            if src is None:
                # Причина называется точно. Прежний текст утверждал, что
                # `articles.json` не объявляет `document`, — и получали его
                # ровно те акты, у которых `articles.json` НЕТ ВОВСЕ. Ложный
                # адрес правки хуже отсутствия причины: автор шёл искать поле
                # в файле, которого не существует.
                why = ("articles.json не объявляет document и рядом нет "
                       f"{'/'.join(SOURCE_DOCUMENTS)}"
                       if act_declaration(act) is not None
                       else "закреплённых байтов в sources/ не найдено — "
                            "фаза 0 не выполнена")
                print(f"{act}: закреплённый документ не разрешён ({why}) — пропущен\n")
                continue
            if not clirs:
                print(f"{act}: CLIR не найден — акт не лоуверен\n")
                continue
            if not first:
                print()
            first = False
            report = depth(src, clirs)
            report["excluded"] = non_normative(act, clirs)
            render(report)
        return 0
    src_path, clir_paths = resolve_paths(args)
    report = depth(src_path, clir_paths)
    if len(args) == 1:
        report["excluded"] = non_normative(args[0], clir_paths)
    render(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
