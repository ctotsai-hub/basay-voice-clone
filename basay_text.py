#!/usr/bin/env python3
"""
basay_text.py — 表記から slug と TTS テキストを派生する（v3 / 2026-04-27）

仕様サマリ:
  ・slug: ŋ/Ŋ/ʔ/'/' → x、ə → e、ɨ → i、英数字以外 → "_"、両端 strip
  ・TTS:
      ⑧ ' / ' / ʔ → x（直前文字に粘着）
      ① 各ワード最初の子音単位の直後に :
      ② 連続子音は最後の子音を複製（例 mn→mnn, tvl→tvll）
      ④ - を : に置換
      ⑤ 語末接尾辞: 直前の母音の前に :、文末以外は , を付加
      ⑥ 語中接尾辞: 前後に :
      ⑦ 助詞 u/ta/nu/i/a の後（文末除く）に ,
      ⑨ 2 音節語は [[...,=]] 形式で出力
  ・接尾辞 longest-match (内側へ反復):
      A: -an -ay -ai -au -na
      B: -ku -ik -su -is -ta -it -mi -am -mu -im -ija
      C: -aku -isu -ita -ami -imu -ia -ja
"""
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

SPECIAL_CHAR_MAP = {
    'ŋ': 'x', 'Ŋ': 'x', 'ʔ': 'x',
    "'": 'x', '’': 'x',
    'ə': 'e', 'ɨ': 'i',
}


_NG_AS_APOS_RE = re.compile(r'([nN])[gG]')


def slug(display, manual=None):
    if manual:
        return re.sub(r'[^a-z0-9_]+', '_', manual.strip().lower()).strip('_')
    s = display or ''
    # 本ユーザ orthography では `ng` は n' (preglottalized n) の入力バリ。
    # n'azi / nxazi / ngazi が同じ slug `nxazi` になるよう統一しておく。
    s = _NG_AS_APOS_RE.sub(lambda m: m.group(1) + 'x', s)
    for src, dst in SPECIAL_CHAR_MAP.items():
        s = s.replace(src, dst)
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    return s.strip('_')


VOWELS = set('aeiouəɨAEIOUƏ')
DIGRAPHS = (
    'tS', 'ts', 'TS', 'Ts',
    # 注意: ng/NG/Ng/nG は本ユーザの orthography では n' (preglottalized n) の
    # 入力バリエーションとして使われるため、digraph として扱わず _parse_units
    # の特殊処理 (cons + 'g'/'x'/apostrophe → 子音複製) に流す。
    'ay', 'AY', 'Ay', 'aY',
    'uy', 'UY', 'Uy', 'uY',
    'oy', 'OY', 'Oy', 'oY',
    'ey', 'EY', 'Ey', 'eY',
    'au', 'AU', 'Au', 'aU',
    'ai', 'AI', 'Ai', 'aI',
)
APOSTROPHES = ("'", '’', 'ʔ')

SUFFIX_GROUPS = {
    'A': ['an', 'ay', 'ai', 'au', 'na', 'i', 'a', ','],
    'B': ['ku', 'ik', 'su', 'is', 'ta', 'it', 'mi', 'am', 'mu', 'im', 'ija'],
    'C': ['aku', 'isu', 'ita', 'ami', 'imu', 'ia', 'ja'],
}
ALL_SUFFIXES_SORTED = sorted(
    set(SUFFIX_GROUPS['A'] + SUFFIX_GROUPS['B'] + SUFFIX_GROUPS['C']),
    key=len, reverse=True
)
PARTICLES = frozenset({'u', 'ta', 'nu', 'i', 'a', 'na'})
ROOT = Path(__file__).resolve().parent
WORD_REWRITE_PATH = ROOT / 'data' / 'word_rewrites.tsv'


def load_word_rewrites(path=WORD_REWRITE_PATH):
    rewrites = {}
    if not path.exists():
        return rewrites
    for line_no, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '\t' in line:
            source, target = line.split('\t', 1)
        else:
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise ValueError(f'{path}:{line_no}: expected SOURCE<TAB>TARGET')
            source, target = parts
        source = source.strip().lower()
        target = target.strip()
        if not source or not target:
            raise ValueError(f'{path}:{line_no}: source and target must be non-empty')
        rewrites[source] = target
    return rewrites


# Reduplicated or lexicalized forms that need a pronunciation-specific
# spelling before the regular TTS rules are applied.
WORD_REWRITE_OVERRIDES = load_word_rewrites()


# digraph 正規化（eSpeak bsy で y が認識されないため、ay→ai 等へ写像）
DIGRAPH_NORMALIZE = {
    'ay': 'ai', 'AY': 'AI', 'Ay': 'Ai', 'aY': 'aI',
    'uy': 'ui', 'UY': 'UI', 'Uy': 'Ui', 'uY': 'uI',
    'oy': 'oi', 'OY': 'OI', 'Oy': 'Oi', 'oY': 'oI',
    'ey': 'ei', 'EY': 'EI', 'Ey': 'Ei', 'eY': 'eI',
}


def _parse_units(word):
    units = []
    i, n = 0, len(word)
    while i < n:
        matched = None
        for dg in DIGRAPHS:
            if word.startswith(dg, i):
                matched = dg
                break
        if matched:
            units.append(DIGRAPH_NORMALIZE.get(matched, matched))
            i += len(matched)
            continue
        ch = word[i]
        # apostrophe または直入力 'x'/'g' (slug/別綴り 形) は
        # 「直前子音の複製」として処理する。これにより:
        #   n'apan / nxapan / ngapan → ['n','n','a','p','a','n']
        #     → [[nn,a,p,a,n,=]]
        # bsy で bracket 内 n+: + n+: + a... のパターンが geminate と等価に
        # 機能する（PC 検証済み）。母音直後の apostrophe は従来通り 'x' 後置。
        # 'x' は n/l/s/z の後 (slug 形)、'g' は n の後のみ (本ユーザ orthography)。
        is_cons_apostrophe = (
            (ch in APOSTROPHES) or
            (ch.lower() == 'x' and units and units[-1] != '-'
             and len(units[-1]) == 1 and units[-1].lower() in 'nlsz') or
            (ch.lower() == 'g' and units and units[-1] != '-'
             and len(units[-1]) == 1 and units[-1].lower() == 'n')
        )
        if is_cons_apostrophe:
            if units and units[-1] != '-':
                last = units[-1]
                if _is_vowel_unit(last):
                    # vowel + ' (kalili' 等) は従来通り 'x' 後置
                    units[-1] = last + 'x'
                else:
                    # consonant + ' / consonant + 'x' は子音複製
                    units.append(last)
            else:
                units.append('x')
            i += 1
            continue
        units.append(ch)
        i += 1
    return units


def _is_vowel_unit(u):
    return bool(u) and u[0] in VOWELS


def _alpha_lower(units):
    return ''.join(u for u in units if u != '-').lower()


def _count_syllables(units):
    count = 0
    in_group = False
    for u in units:
        if u == '-':
            in_group = False
            continue
        if _is_vowel_unit(u):
            if not in_group:
                count += 1
                in_group = True
        else:
            in_group = False
    return count


def _strip_one_end_suffix(alpha):
    for suf in ALL_SUFFIXES_SORTED:
        if len(alpha) > len(suf) and alpha.endswith(suf):
            return alpha[:-len(suf)], suf
    return None


def _count_units_for_chars(units, n_chars):
    total = 0
    for i in range(len(units) - 1, -1, -1):
        if units[i] == '-':
            continue
        total += len(units[i])
        if total == n_chars:
            return len(units) - i
        if total > n_chars:
            return None
    return None if total != n_chars else len(units)


def _count_consonant_units(units):
    return sum(1 for u in units if u != '-' and not _is_vowel_unit(u))


def _segment_word(units):
    suffix_chunks = []
    remaining = units[:]
    while True:
        alpha = _alpha_lower(remaining)
        result = _strip_one_end_suffix(alpha)
        if result is None:
            break
        _, suf = result
        cnt = _count_units_for_chars(remaining, len(suf))
        if cnt is None or cnt == 0 or cnt >= len(remaining):
            break
        next_remaining = remaining[:-cnt]
        if _count_syllables(next_remaining) == 0 and _count_consonant_units(next_remaining) > 1:
            break
        suffix_chunks.append(remaining[-cnt:])
        remaining = next_remaining
    segments = [(remaining, 'stem')]
    if suffix_chunks:
        suffix_chunks.reverse()
        for j, chunk in enumerate(suffix_chunks):
            kind = 'end' if j == len(suffix_chunks) - 1 else 'mid'
            segments.append((chunk, kind))
    return segments


def _last_unit(stem, up_to_idx):
    for j in range(up_to_idx - 1, -1, -1):
        if stem[j] != '-':
            return stem[j]
    return ''


def _last_consonant_run_length(units, up_to_idx):
    count = 0
    for j in range(up_to_idx - 1, -1, -1):
        u = units[j]
        if u == '-':
            break
        if _is_vowel_unit(u):
            break
        count += 1
    return count


def _render_consonant_run(run):
    if not run:
        return ''
    rendered = ''.join(run)
    if len(run) > 1 and run[-1].lower() != run[-2].lower():
        rendered += run[-1]
    return rendered


def _render_stem(stem):
    if not stem:
        return ''
    out = []
    found_first_vowel = False
    last_run_len = 0
    i = 0
    while i < len(stem):
        u = stem[i]
        if u == '-':
            out.append(':')
            found_first_vowel = True
            last_run_len = 0
            i += 1
            continue
        if _is_vowel_unit(u):
            if not found_first_vowel and last_run_len == 1:
                out.append(':')
            out.append(u)
            found_first_vowel = True
            last_run_len = 0
            i += 1
        else:
            j = i
            run = []
            while j < len(stem) and stem[j] != '-' and not _is_vowel_unit(stem[j]):
                run.append(stem[j])
                j += 1
            out.append(_render_consonant_run(run))
            last_run_len = len(run)
            i = j
    return ''.join(out)


def _suffix_starts_with_vowel(units):
    for u in units:
        if u == '-':
            continue
        return _is_vowel_unit(u)
    return False


def _render_suffix(suf):
    if not suf:
        return ''
    if _suffix_starts_with_vowel(suf):
        return ''.join(u for u in suf if u != '-')
    out = []
    inserted = False
    for u in suf:
        if u == '-':
            continue
        if not inserted and _is_vowel_unit(u):
            out.append(':')
            inserted = True
        out.append(u)
    return ''.join(out)


def _process_segments(segments):
    parts = []
    for units, kind in segments:
        if kind == 'stem':
            parts.append(_render_stem(units))
        elif kind == 'mid':
            inner = _render_suffix(units)
            if _suffix_starts_with_vowel(units):
                parts.append(':' + inner + ':')
            else:
                parts.append(inner + ':')
        elif kind == 'end':
            inner = _render_suffix(units)
            if _suffix_starts_with_vowel(units):
                parts.append(':' + inner)
            else:
                parts.append(inner)
    joined = ''.join(parts)
    while '::' in joined:
        joined = joined.replace('::', ':')
    return joined


def _format_2syl_brackets(units):
    """rule ⑨：2 音節語は [[ phonemes,= ]] 形式（全て小文字）。
    分離ルール:
      ・先頭子音群 → 最初の母音: :
      ・母音 → 子音: ,
      ・連続子音: 最後の子音を複製
      ・子音 → 母音 / 母音 → 母音: ,
    例：paman → [[p:a,m,a,n,=]]
        palsu → [[p:a,lss,u,=]]（語中 ls クラスタ）
        ita   → [[i,t,a,=]]、abu → [[a,b,u,=]]"""
    parts = []
    found_first_vowel = False
    prev_is_vowel = False
    last_run_len = 0
    i = 0
    while i < len(units):
        u = units[i]
        if u == '-':
            last_run_len = 0
            i += 1
            continue
        u_low = u.lower()
        if _is_vowel_unit(u):
            if not found_first_vowel:
                if parts:
                    if last_run_len > 1:
                        parts.append(',' + u_low)
                    else:
                        parts.append(':' + u_low)  # 子音 → 最初の母音
                else:
                    parts.append(u_low)        # 母音始まり
            else:
                parts.append(',' + u_low)      # 母音 → 母音 or 子音 → 母音
            found_first_vowel = True
            prev_is_vowel = True
            last_run_len = 0
            i += 1
        else:
            j = i
            run = []
            while j < len(units) and units[j] != '-' and not _is_vowel_unit(units[j]):
                run.append(units[j].lower())
                j += 1
            rendered = _render_consonant_run(run)
            if not parts:
                parts.append(rendered)
            elif prev_is_vowel:
                parts.append(',' + rendered)   # 母音 → 子音
            else:
                parts.append(rendered)
            prev_is_vowel = False
            last_run_len = len(run)
            i = j
    return '[[' + ''.join(parts) + ',=]]'


_TRAIL_PUNCT_RE = re.compile(r"[^A-Za-zəɨŋŊ'’ʔ\-]+$")
_LEAD_PUNCT_RE = re.compile(r"^[^A-Za-zəɨŋŊ'’ʔ\-]+")


def _process_token(token, is_final):
    if not token:
        return token
    lead = ''
    bare = token
    m = _LEAD_PUNCT_RE.match(bare)
    if m:
        lead = m.group(0)
        bare = bare[len(lead):]
    trail = ''
    m = _TRAIL_PUNCT_RE.search(bare)
    if m:
        trail = m.group(0)
        bare = bare[:-len(trail)]
    if not bare:
        return token

    tts_bare = WORD_REWRITE_OVERRIDES.get(bare.lower(), bare)
    units = _parse_units(tts_bare)
    segments = _segment_word(units)
    if _count_syllables(units) == 2:
        rendered = _format_2syl_brackets(units)
    else:
        rendered = _process_segments(segments)

    bare_alpha_lower = _alpha_lower(units)
    has_end_suffix = bool(segments and segments[-1][1] == 'end')
    is_particle = bare_alpha_lower in PARTICLES
    trail_has_comma = ',' in trail
    if (has_end_suffix or is_particle) and not is_final and not trail_has_comma:
        if not rendered.endswith(','):
            rendered = rendered + ','
    # TTS 全体を小文字化（eSpeak で大文字が音素名と衝突するため）
    return (lead + rendered + trail).lower()


def tts_text(display, manual=None):
    if manual is not None and manual != '':
        return manual
    if not display or not display.strip():
        return ''
    tokens = display.split()
    n = len(tokens)
    out = []
    for i, tok in enumerate(tokens):
        out.append(_process_token(tok, is_final=(i == n - 1)))
    return ' '.join(out)


def derive(display, slug_override=None, tts_override=None):
    return {
        'display': display,
        'slug': slug(display, slug_override),
        'tts': tts_text(display, tts_override),
    }


TEST_CASES = [
    # 1 音節 / 3+ 音節：bracket 不使用、出力小文字
    ("Makawas",   "makawas",   "m:akawas"),
    ("mau",       "mau",       "m:au"),
    ("tsu",       "tsu",       "ts:u"),
    ("amaku",     "amaku",     "am:aku"),
    ("kumanisu",  "kumanisu",  "k:um:an:isu"),
    ("kalili'",   "kalilix",   "k:alilix"),
    # 2 音節：bracket [[..,=]]（diphthong ay/au/ai 1 ユニット、連続子音は末尾子音複製）
    ("ita",       "ita",       "[[i,t,a,=]]"),
    ("Basay",     "basay",     "[[b:a,s,ai,=]]"),
    ("lusa",      "lusa",      "[[l:u,s,a,=]]"),
    ("zanum",     "zanum",     "[[z:a,n,u,m,=]]"),
    ("batu",      "batu",      "[[b:a,t,u,=]]"),
    ("abu",       "abu",       "[[a,b,u,=]]"),
    ("paman",     "paman",     "[[p:a,m,a,n,=]]"),
    ("kuman",     "kuman",     "[[k:u,m,a,n,=]]"),
    ("paslin",    "paslin",    "[[p:a,sll,i,n,=]]"),
    ("palsu",     "palsu",     "[[p:a,lss,u,=]]"),
    # n' / nx (slug 形) は子音複製で 2 つの n unit にする。
    # 例: [[nn,a,p,a,n,=]] が geminate + final stress を両立させる
    ("n'apan",    "nxapan",    "[[nn,a,p,a,n,=]]"),
    ("qumnipa",   "qumnipa",   "q:umnnip:a"),
    ("tvlakuki",  "tvlakuki",  "tvllakuk:i"),
    ("vlay",      "vlay",      "vpllai"),
    ("vavan",     "vavan",     "[[v:a,pvv,a,n,=]]"),
    # 多語フレーズ
    ("paman tisu",
     "paman_tisu",
     "[[p:a,m,a,n,=]], [[t:i,s,u,=]]"),
    ("Makawas ita mau Basay",
     "makawas_ita_mau_basay",
     "m:akawas [[i,t,a,=]], m:au, [[b:a,s,ai,=]]"),
]


def run_tests():
    print("basay_text.py self-test (v3, [[ ]] accent)")
    print("=" * 64)
    fail = 0
    for display, exp_slug, exp_tts in TEST_CASES:
        d = derive(display)
        s_ok = d['slug'] == exp_slug
        t_ok = d['tts'] == exp_tts
        mark = "OK" if (s_ok and t_ok) else "NG"
        if not (s_ok and t_ok):
            fail += 1
        print("[" + mark + "] " + repr(display))
        if not s_ok:
            print("    slug got " + repr(d['slug']) + " expected " + repr(exp_slug))
        if not t_ok:
            print("    tts  got " + repr(d['tts']) + " expected " + repr(exp_tts))
    print("Result: " + str(len(TEST_CASES) - fail) + "/" + str(len(TEST_CASES)) + " passed")
    return 0 if fail == 0 else 1


def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__, file=sys.stderr)
        return 0
    if args[0] == '--test':
        return run_tests()
    slug_override = None
    tts_override = None
    rest = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--slug' and i + 1 < len(args):
            slug_override = args[i + 1]
            i += 2
            continue
        if a == '--tts' and i + 1 < len(args):
            tts_override = args[i + 1]
            i += 2
            continue
        rest.append(a)
        i += 1
    text = ' '.join(rest)
    d = derive(text, slug_override, tts_override)
    print("display\t" + d['display'])
    print("slug\t" + d['slug'])
    print("tts\t" + d['tts'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
