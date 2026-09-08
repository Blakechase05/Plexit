/* ============================================================
   Light Fitting Schedule - v4
   Tabs: Datasheets (drop & scan) | Schedule (the LFS)
   Drop a PDF/IES on the big dropzone, on the table, or on a
   specific row. Scans run concurrently with per-file progress.
   Fields not found by the scan are highlighted until filled.
   ============================================================ */

'use strict';

/* ==================== COLUMNS ==================== */

const COLS = [
    { key: 'tag',        label: 'TAG',                  px: 60,  xw: 8.4 },
    { key: 'description',label: 'DESCRIPTION',          px: 200, xw: 35 },
    { key: 'location',   label: 'LOCATION',             px: 135, xw: 23.4 },
    { key: 'finish',     label: 'FINISH',               px: 95,  xw: 14 },
    { key: 'dimensions', label: 'DIMENSIONS',           px: 135, xw: 20.3 },
    { key: 'ip',         label: 'IP RATING',            px: 78,  xw: 18 },
    { key: 'source',     label: 'LIGHT SOURCE',         px: 110, xw: 23 },
    { key: 'cri',        label: 'CRI',                  px: 58,  xw: 9.6 },
    { key: 'sdcm',       label: 'SDCM',                 px: 62,  xw: 12.3 },
    { key: 'lifetime',   label: 'LIFETIME',             px: 95,  xw: 12.3 },
    { key: 'mounting',   label: 'MOUNTING',             px: 140, xw: 25.3 },
    { key: 'driver',     label: 'DRIVER',               px: 90,  xw: 15.4 },
    { key: 'control',    label: 'CONTROL',              px: 145, xw: 30 },
    { key: 'model',      label: 'MANUFACTURER / MODEL', px: 240, xw: 49.7 }
];

/* Cells the scanners try to fill (location included so it's flagged for the user);
   used for "needs fill" highlighting */
const SCAN_TARGET_KEYS = ['description', 'location', 'finish', 'dimensions', 'ip', 'source',
    'cri', 'sdcm', 'lifetime', 'mounting', 'driver', 'control', 'model'];

/* Known lighting suppliers/manufacturers, checked against datasheet text */
const SUPPLIERS = [
    'FAZE', 'UNIOS', 'EAGLE LIGHTING', 'CLEVERTRONICS', 'ARKOSLIGHT', 'DIGILIN', 'ERCO',
    'KLIK SYSTEMS', 'ROXO', 'WEVER & DUCRE', 'WEVER AND DUCRE', 'IGUZZINI', 'EWO',
    'PIERLITE', 'LIGMAN', 'WE-EF', 'SIMES', 'DELTA LIGHT', 'XAL', 'FAGERHULT',
    'LOUIS POULSEN', 'VIBIA', 'IBL', 'VERSALUX', 'MSL', 'LPE'
];

function detectSupplier(text) {
    const up = text.toUpperCase();
    for (const name of SUPPLIERS) {
        const re = new RegExp('\\b' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b');
        if (re.test(up)) return name;
    }
    return '';
}

/* ==================== BOLD MARKUP ====================
   Cell values are plain text with **bold** runs. Rendered as <b> in the
   table (Ctrl+B toggles bold while editing) and as rich text on export. */

function stripMd(s) { return String(s || '').replace(/\*\*/g, ''); }

/* Schedules are written in capitals, but units are not: 89mm, 1049lm, >50,000h.
   Uppercase everything, then put the unit suffixes back to lower case. */
function scheduleCase(s) {
    return String(s || '').toUpperCase()
        .replace(/(\d)\s*MM\b/g, '$1mm')
        .replace(/(\d)\s*LM\b/g, '$1lm')
        .replace(/(\d)\s*HRS?\b/g, '$1h')
        .replace(/(\d)\s*H\b/g, '$1h')
        .replace(/(lm|\dW)\s*\/\s*M\b/g, '$1/m')
        .replace(/\bLM\s*\/\s*W\b/g, 'lm/W')
        .replace(/\bLUX\b/g, 'lux')
        .replace(/([)\dm])\s+X\s+/g, '$1 x ');
}

function mdToHtml(s) {
    return esc(s)
        .replace(/\*\*([^*\n][^*]*?)\*\*/g, '<b>$1</b>')
        .replace(/\n/g, '<br>');
}

function htmlToMd(node, inBold) {
    let out = '';
    node.childNodes.forEach(n => {
        if (n.nodeType === 3) { out += n.nodeValue; return; }
        if (n.nodeType !== 1) return;
        const tag = n.tagName;
        if (tag === 'BR') { out += '\n'; return; }
        const isBold = !inBold && (tag === 'B' || tag === 'STRONG' ||
            (n.style && (n.style.fontWeight === 'bold' || parseInt(n.style.fontWeight, 10) >= 600)));
        if (/^(DIV|P)$/.test(tag) && out && !out.endsWith('\n')) out += '\n';
        const inner = htmlToMd(n, inBold || isBold);
        out += isBold
            ? inner.split('\n').map(l => l.trim() ? '**' + l + '**' : l).join('\n')
            : inner;
    });
    return out;
}

/* Excel rich text from **bold** markup */
function mdToRich(text, baseFont) {
    if (!text.includes('**')) return null;
    const runs = [];
    text.split(/(\*\*[^*]+\*\*)/).forEach(part => {
        if (!part) return;
        if (part.startsWith('**') && part.endsWith('**')) {
            runs.push({ text: part.slice(2, -2), font: { ...baseFont, bold: true } });
        } else {
            runs.push({ text: part, font: baseFont });
        }
    });
    return { richText: runs };
}

/* ==================== TAG -> DESCRIPTION ==================== */

const TAG_DESC = [
    ['PL', 'POLE LIGHT'],
    ['BL', 'BOLLARD'],
    ['EM', 'EMERGENCY LIGHT'],
    ['EX', 'EXIT SIGN'],
    ['FL', 'FLOOR LIGHT'],
    ['EL', 'EXAMINATION LIGHT'],
    ['SL', 'STRIP LIGHT'],
    ['TL', 'TABLE LAMP'],
    ['D', 'DOWNLIGHT'],
    ['A', 'PANEL LIGHT'],
    ['P', 'PENDANT'],
    ['B', 'BATTEN'],
    ['W', 'WALL LIGHT']
]; // longest prefixes first so PL wins over P, BL over B, etc.

function descFromTag(tag) {
    let letters = (String(tag).trim().toUpperCase().match(/^[A-Z]+/) || [''])[0];
    while (letters) {
        const hit = TAG_DESC.find(([p]) => letters === p);
        if (hit) return hit[1];
        // 'X' can stand in for the number (DX, AX, PLX...) - trim it and retry
        if (letters.endsWith('X')) letters = letters.slice(0, -1);
        else break;
    }
    return '';
}

const AUTO_DESCS = new Set(TAG_DESC.map(([, d]) => d));

/* ==================== LABEL-DRIVEN EXTRACTION ====================
   Most manufacturers publish a "label  value" specification table. Reading
   those pairs is far more reliable than pattern-matching the whole document,
   which picks up packaging sizes, order codes and marketing copy.
   Labels are listed most-specific first. */

const SPEC_LABELS = {
    /* 'description' deliberately excluded: on many sheets it heads a prose paragraph,
       which then becomes the product name. */
    name:     ['product name', 'product family', 'family name', 'name', 'designation'],
    code:     ['product code', 'reference', 'order code', 'article number',
               'catalogue number', 'catalog number', 'item code', 'sku'],
    finish:   ['finish colour', 'finish color', 'finish', 'colour', 'color'],
    voltage:  ['input voltage', 'supply voltage', 'operating voltage', 'mains voltage'],
    illuminance: ['illumination', 'illuminance'],
    category: ['mounting location', 'ceiling type/mounting', 'category', 'installation type', 'installation',
               'mounting type', 'mounting'],
    lumens:   ['rated luminaire luminous flux', 'luminous flux of the luminaire',
               'gross luminous flux', 'luminous flux', 'nominal flux', 'delivered lumens',
               'system lumens [lm]', 'luminaire lumens [lm]', 'led lumens', 'output (lm)',
               'light output', 'lumen output', 'lumens', 'lumen', 'output', 'lamp'],
    diameter: ['w = width/diameter [mm]', 'luminaire width', 'diameter', 'dia', 'width'],
    height:   ['h = height [mm]', 'luminaire height', 'height', 'overall height'],
    length:   ['l = length [mm]', 'length'],
    cct:      ['colour temperature', 'color temperature', 'cct/wavelength', 'cct / cri',
               'spectrum', 'cct'],
    sdcm:     ['chromatic stability', 'colour consistency', 'color consistency',
               'colour tolerance', 'standard deviation color matching',
               'standard deviation colour matching', 'colour deviation', 'color deviation',
               'macadam', 'sdcm', 'binning'],
    cri:      ['colour rendering index', 'color rendering index', 'colour rendering',
               'colour rendition index', 'color rendition index', 'cct / cri', 'typical cri', 'cri'],
    watts:    ['power values of the system', 'system power', 'luminaire power',
               'power consumption', 'total power', 'wattage [w]', 'wattage', 'watts', 'power'],
    ledWatts: ['rated module power', 'led module', 'wattage [w]', 'luminaire power',
               'watt/m', 'power', 'led', 'lamp'],
    lifetime: ['lifetime l90b10', 'lifetime l80b10', 'lifetime led 1', 'lifetime led',
               'led lifetime', 'led lifespan', 'lifespan',
               'l90', 'l80', 'l70', 'lumen maintenance', 'l100b50 lifetime (clo) [hrs]',
               'l90b50 lifetime [hrs]', 'tm21 l90 reported lifetime [hrs]',
               'tm21 l70 reported lifetime [hrs]', 'led performance', 'lifetime',
               'rated life', 'service life'],
    beam:     ['light beam angle', 'beam angle', 'beamwidth (fwhm)', 'beam angles',
               'beam spread', 'beam'],
    dimming:  ['driver control', 'control gear', 'control type', 'dimming', 'dimmable',
               'control protocol', 'control'],
    driver:   ['driver', 'control gear', 'gear'],
    ip:       ['protection class ip', 'luminaire ip rating', 'sealing', 'ingress protection', 'ip rating',
               'protection rating', 'protection degree', 'degree of protection'],
    recess:   ['recess measurements', 'recess dimensions', 'cutout size', 'cut-out size',
               'cut-out', 'cut out', 'cutout', 'aperture'],
    dims:     ['general (mm)', 'product dimensions', 'fixture dimensions', 'luminaire dimensions',
               'overall dimensions', 'dimensions']
};

/* Words that, appearing just before a label, mean it is the WRONG value
   (e.g. "Packaging dimensions 273 x 143 x 75 mm" is not the fitting size) */
const LABEL_EXCLUDE = /(packag|carton|box|shipping|gross weight|pallet|bend|bending|radius|minimum|max(?:imum)?\s+cable)\s*\S{0,12}$/i;

/* Per-field traps: "LED Colour: White" is the light colour, not the fitting finish */
const LABEL_EXCLUDE_BY_KEY = {
    finish: /\b(led|light|lamp|body|beam)\s*$/i
};

/* A value listing every option the range offers ("Mains/Phase, DALI, DMX, Bluetooth")
   is a menu, not this fitting's specification - never scheduled as fact. */
/* "906 - 1112 lm" / "91 - 111 lm/W" spans the range's variants - no single value
   applies to the fitting in front of you. */
function isNumericRange(v) {
    /* "906 - 1112 lm", "7050...7400 lm", "85,,,88 W" - all span a range's variants */
    return /\d[\d,. ]*\s*(?:[-–]|\.{2,}|,{2,})\s*\d[\d,. ]*\s*(lm|w|k|lx)\b/i.test(v) ||
        /^\s*\d[\d,.]*\s*(?:[-–]|\.{2,}|,{2,})\s*\d[\d,.]*\s*$/.test(v.trim());
}

function isOptionList(v) {
    if ((v.match(/,/g) || []).length >= 2) return true;
    if (/\bavailable\b|please consult|varies with|requires|compatible with/i.test(v)) return true;
    return v.length > 42 && (v.match(/\s/g) || []).length >= 5;   // a sentence, not a spec
}

/* Dimensions quoted for more than one variant ("Surface: ... / Recessed: ...") */
function hasVariants(v) {
    return /\b(surface|recessed|standard|shallow|deep|version|option)\b\s*[:\-]/i.test(v) ||
        (v.match(/\//g) || []).length >= 1 && /\b(version|body|standard)\b/i.test(v) ||
        (v.match(/\bmm\b/gi) || []).length > 3;
}

function escRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

/* Some manufacturers letter-space their headings ("WAT TA G E", "DIAME TE R").
   Matching is done on a space-free copy of each line so the spacing is irrelevant. */
const LIGATURES = { 'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ﬅ': 'ft', 'ﬆ': 'st' };
function deligature(s) { return String(s).replace(/[ﬀﬁﬂﬃﬄﬅﬆ]/g, c => LIGATURES[c] || c); }
function squash(s) { return deligature(s).replace(/\s+/g, '').toLowerCase(); }

/* Original column index of the Nth non-space character in a line */
function colOfNonSpace(line, n) {
    let seen = 0;
    for (let i = 0; i < line.length; i++) {
        if (!/\s/.test(line[i])) {
            if (seen === n) return i;
            seen++;
        }
    }
    return line.length;
}

/* Value that belongs to a label. Handles three layouts:
     "Label   Value"          (value beside the label)
     "Label"                  (value on the next line, same column - two-column sheets)
     "Label: Value"
   Occurrences preceded by an excluded word (packaging, cut-out...) are skipped. */
/* Fields whose value is normally words, not a number with a unit */
const TEXT_VALUE_KEYS = new Set(['name', 'finish', 'category', 'mounting']);

function labelValue(text, key, span = 64, onlyLabel, validate) {
    const lines = String(text).split('\n');
    const squashedLines = lines.map(squash);

    for (const label of (onlyLabel ? [onlyLabel] : (SPEC_LABELS[key] || []))) {
        const sl = squash(label);
        for (let i = 0; i < lines.length; i++) {
            const pos = squashedLines[i].indexOf(sl);
            if (pos < 0) continue;

            const line = lines[i];
            const startCol = colOfNonSpace(line, pos);
            /* one past the label's last character - NOT the next non-space char,
               or the gap to the next column is lost and its heading looks like a value */
            const endCol = colOfNonSpace(line, pos + sl.length - 1) + 1;

            /* guard: is this the wrong "dimensions" (packaging, cut-out, bend...)? */
            const before = line.slice(Math.max(0, startCol - 26), startCol);
            if (LABEL_EXCLUDE.test(before + ' ')) continue;
            if (LABEL_EXCLUDE_BY_KEY[key] && LABEL_EXCLUDE_BY_KEY[key].test(before)) continue;
            /* A label must start a word. Test the ORIGINAL line, not the squashed
               copy: in a two-column row "CCT  4000K   CRI  Ra90" the squashed text
               reads "...4000kcri..." and CRI would look like it sits inside a word. */
            if (startCol > 0 && /[a-z0-9]/i.test(line[startCol - 1])) continue;

            /* the next line that could hold a value */
            let nextLine = null;
            for (let j = i + 1; j < Math.min(i + 3, lines.length); j++) {
                if (lines[j].trim()) { nextLine = lines[j]; break; }
            }
            /* If a word begins at exactly this column on the following line, this is a
               row of HEADINGS with the values underneath (two-column sheets). If the
               next line merely overlaps the column it is a different right-aligned
               label, and the value sits beside this one instead. */
            const valuesBelow = !!nextLine && startCol < nextLine.length &&
                /\S/.test(nextLine[startCol]) && (startCol === 0 || /\s/.test(nextLine[startCol - 1]));

            /* 1. value on the same line, after the label */
            let tail = line.slice(endCol);

            /* A real label is followed by a separator - a colon, a dash, a column gap,
               or the end of the line. Without this, "Delivered lumens and system W/m
               may vary" and the filename "...SymRef-LED1000lm..." both look like
               labelled fields. */
            if (!/^\s*$|^\s*[:\-–]|^\s{2,}|^\s*[[(]/.test(tail)) continue;
            const hadColon = /^\s*[:\-–]/.test(tail);
            tail = tail.replace(/^\s*:/, '');

            /* a trailing unit belongs to the label, not the value: "CCT [K]", "Width (m)" */
            const unit = tail.match(/^\s*[[(]([^\])]{1,8})[\])]/);
            let unitWord = '';
            if (unit) { unitWord = unit[1].trim(); tail = tail.slice(unit[0].length); }
            const gap = (tail.match(/^\s*/) || [''])[0].length;
            const parts = tail.split(/\s{3,}/).map(s => s.trim()).filter(Boolean);

            /* Several columns after the label means a variant table
               ("Red Green Blue White Combined", "500mm version ... 1000mm version").
               No single value applies to this fitting, so do not guess one.
               Measured fields are stricter: even two columns means two variants. */
            /* diameter/height/length are single-value fields that commonly sit beside
               an unrelated column ("Diameter Ø89mm   Cutout Size Ø76mm"), so they use
               the looser threshold. 'dims' stays strict - it really carries variants. */
            const MEASURED = ['dims', 'lumens', 'watts', 'ledWatts', 'cct', 'cri', 'beam', 'lifetime'];
            /* Only count columns carrying the SAME kind of quantity. A drawing note
               ("Imax=4577cd") or a column of prose beside the spec is not a variant. */
            const UNIT = {
                watts: /\d\s*W\b/i, ledWatts: /\d\s*W\b/i, lumens: /\d\s*lm\b/i,
                cct: /\d\s*°?\s*K\b/, dims: /\d\s*mm\b/i, diameter: /\d\s*mm\b/i,
                height: /\d\s*mm\b/i, length: /\d\s*mm\b/i, beam: /\d\s*°/,
                lifetime: /\d{3,}|L\d{2,3}/i,
                cri: /^\s*(cri|ra)?\s*[>≥]?\s*\d{2}\s*\+?\.?\s*$/i
            };
            const unitRe = UNIT[key];
            const valueish = parts.filter(pt => unitRe
                ? unitRe.test(pt)
                : /\d/.test(pt) && (pt.length <= 24 || /\b(mm|lm|W|K|hrs?|V)\b/i.test(pt)));
            if (valueish.length >= (MEASURED.includes(key) ? 2 : 3)) continue;

            /* A small gap followed by another column means the real label is longer
               than the one we matched ("Colour" inside "Colour Consistency (LED)"). */
            if (gap < 3 && parts.length >= 2 && !hadColon) continue;

            /* Gather both candidates - beside the label, and below it - then let the
               caller's validator decide which is actually this field's value. That
               beats guessing the sheet's layout: "CCT [K]   R9" / "4000K   70" has a
               plausible-looking value in both places, but only one is a colour temp. */
            const candidates = [];
            const rest = tail.replace(/^\s*[:\-–]?\s*/, '').split(/\s{3,}/)[0].trim();
            /* valueLike() only recognises numbers-with-units, so on a sheet that
               also stacks values under labels a WORD value beside its label was
               being thrown away: "Name   DIVI INDIRECT END" fell through and the
               next line's label ("Reference") was read as the product name.
               Word values for the text fields are legitimate candidates. */
            const wordValue = TEXT_VALUE_KEYS.has(key) && /^[A-Za-z]/.test(rest) &&
                rest.split(/\s+/).length <= 8;
            if (rest && !isLabelLike(rest) && !isNotApplicable(rest) &&
                (gap < 3 || valueLike(rest) || !valuesBelow || wordValue)) {
                /* re-attach a unit the label was carrying, so "Width (m)  0.093"
                   is read as metres rather than a bare number */
                candidates.push((unitWord && /^[\d.,]+$/.test(rest.trim())
                    ? rest.trim() + ' ' + unitWord : rest).slice(0, span));
            }
            if (nextLine) {
                const from = Math.max(0, startCol - 3);
                const v = nextLine.slice(from).replace(/^\s+/, '').split(/\s{3,}/)[0].trim();
                if (v && !isLabelLike(v) && !isNotApplicable(v)) candidates.push(v.slice(0, span));
            }
            if (!candidates.length) continue;
            if (!validate) return candidates[0];
            const good = candidates.find(validate);
            if (good) return good;
        }
    }
    return '';
}

/* Datasheets use "-" or "N/A" to mean the field does not apply. Keep looking. */
function isNotApplicable(s) {
    return /^(-+|–|—|n\/?a|tbc|tba|please consult|consult)\.?$/i.test(s.trim());
}

/* A value that is really another heading (unit bracket, or all-caps words) */
function isLabelLike(s) {
    return /\[[^\]]*\]\s*$/.test(s) || (/^[A-Z0-9 ()\/.\-]{6,}$/.test(s) && !/\d/.test(s));
}

/* Does this text read like a measured value rather than a neighbouring heading? */
function valueLike(s) {
    const v = s.trim();
    if (/^[<>≤≥~]?\s*[Ø⌀]?\s*\d/.test(v)) return true;      // 700 lm, 4000K, 12
    if (/^[A-Z][a-z]/.test(v)) return true;                 // Recessed, Ra90+, Grey Matt
    if (/^[A-Z]{1,4}\d/.test(v)) return true;               // IP20, IK07, L90B10
    if (/^[A-Z0-9][A-Z0-9\/\-]{1,7}$/.test(v)) return true; // DMX, DALI, WALL - one token
    if (/^(yes|no|n\/a|-|included|excluded|compliant)\b/i.test(v)) return true;
    return false;
}

/* Does the document publish this field at all? If it does but labelValue found
   nothing usable, the field is ambiguous (variant table, "please consult") and we
   must NOT fall back to scanning prose - that is where wrong numbers come from. */
function hasLabel(text, key) {
    const lines = String(text).split('\n');
    const squashed = lines.map(squash);
    return (SPEC_LABELS[key] || []).some(label => {
        const sl = squash(label);
        return lines.some((line, i) => {
            const pos = squashed[i].indexOf(sl);
            if (pos < 0) return false;
            const startCol = colOfNonSpace(line, pos);
            if (startCol > 0 && /[a-z0-9]/i.test(line[startCol - 1])) return false;
            const endCol = colOfNonSpace(line, pos + sl.length - 1) + 1;
            return /^\s*$|^\s*[:\-–]|^\s{2,}|^\s*[[(]/.test(line.slice(endCol));
        });
    });
}

/* Like labelValue, but also reports which label matched - needed when the
   label itself carries information (e.g. "L100B50 LIFETIME [HRS]" -> 50000) */
function labelValueLabelled(text, key, span = 64) {
    for (const label of (SPEC_LABELS[key] || [])) {
        const one = labelValue(text, key, span, label, key === 'lifetime' ? (x => /\d{3,}|L\d{2,3}/i.test(x)) : undefined);
        if (one) return { label, value: one };
    }
    return { label: '', value: '' };
}

/* Numbers: "4,5" is 4.5 in most of Europe; "60.000h" is 60,000 hours */
function normDecimal(s) {
    return String(s).replace(/(\d),(\d{1,2})(?!\d)/g, '$1.$2');
}

function normThousands(s) {
    return String(s).replace(/(\d)\.(\d{3})\b/g, '$1,$2');
}

function firstNumber(s) {
    const m = normDecimal(s).match(/-?\d+(?:\.\d+)?/);
    return m ? m[0] : '';
}

function tidyNum(n) {
    return String(parseFloat(n)).replace(/\.0$/, '');
}

/* ==================== SPEC DETECTORS (shared by IES + PDF scans) ==================== */

/* Fitting type, e.g. "RECESSED DOWNLIGHT", "STRIP LIGHT" */
function detectDescription(text) {
    const TYPES = [
        [/operating\s*theatre|examination\s*light|surgical/i, 'EXAMINATION LIGHT'],
        [/t-?bar|troffer/i, 'TROFFER'],
        [/continuous\s*luminaire|end\s*luminaire|linear\s*luminaire/i, 'LINEAR EXTRUSION'],
        [/wall\s*wash/i, 'WALL WASHER'],
        [/wall\s*graz/i, 'WALL GRAZER'],
        [/down\s*light|downlight/i, 'DOWNLIGHT'],
        [/troffer/i, 'TROFFER'],
        [/panel\s*light|led\s*panel/i, 'PANEL'],
        [/batten/i, 'BATTEN'],
        /* "flex" alone is usually the cable ("AUS flex & plug"), not a flexible strip */
        [/strip\s*light|led\s*strip|led\s*tape|flexible\s*(strip|tape)|neon\s*flex/i, 'STRIP LIGHT'],
        [/extrusion|profile|linear/i, 'LINEAR EXTRUSION'],
        [/pendant/i, 'PENDANT'],
        [/track/i, 'TRACK LIGHT'],
        [/spot\s*light|spotlight|\bspot\b/i, 'DOWNLIGHT'],   // a spot is scheduled as a downlight
        [/high\s*bay/i, 'HIGH BAY'],
        [/flood/i, 'FLOODLIGHT'],
        [/bollard/i, 'BOLLARD'],
        [/step\s*light/i, 'STEP LIGHT'],
        [/in-?ground|inground/i, 'IN GROUND LIGHT'],
        [/oyster/i, 'OYSTER'],
        [/wall\s*light|wall-?mounted|bracket/i, 'WALL LIGHT']
    ];
    for (const [re, name] of TYPES) {
        if (re.test(text)) {
            /* no 'RECESSED ' prefix: DESCRIPTION is the fitting type, the
               MOUNTING column carries how it is installed */
            if (false) {
                return name;
            }
            return name;
        }
    }
    return '';
}

/* Description from the two sources a manufacturer actually asserts: the product
   name/headline, then their own category field. Marketing prose is deliberately
   NOT used - a paragraph mentioning "linear" or "recessed" turned a bedside wall
   light into a linear extrusion. If neither source is clear, leave it blank so
   the cell stays flagged rather than guessed. */
function describeFitting(name, category) {
    const fromName = name ? detectDescription(name) : '';
    const recessed = /RECESS/i.test(category || '');
    if (fromName) {
        /* a linear extrusion or strip is described by what it is, not how it is fixed */
        return fromName;
    }
    return categoryToDescription(category);
}

/* Last-resort description from the manufacturer's own category field */
function categoryToDescription(cat) {
    if (!cat || cat.length > 34 || /[;.]/.test(cat)) return '';
    const c = cat.toUpperCase();
    if (/T-?BAR|GRID/.test(c)) return 'TROFFER';
    if (/LINEAR|EXTRUSION|PROFILE/.test(c)) return 'LINEAR EXTRUSION';
    if (/T-?BAR|GRID/.test(c)) return 'TROFFER';
    if (/CEILING\s*RECESS/.test(c)) return 'DOWNLIGHT';
    if (/CEILING\s*SURFACE/.test(c)) return 'SURFACE MOUNTED DOWNLIGHT';
    if (/^WALL\b|WALL\s*(LIGHT|LUMINAIRE)/.test(c)) return 'WALL LIGHT';
    if (/FLOOR|IN[\s-]?GROUND/.test(c)) return 'FLOOR LIGHT';
    if (/SUSPEND|PENDANT/.test(c)) return 'PENDANT';
    if (/TRACK/.test(c)) return 'TRACK LIGHT';
    if (/TABLE|PORTABLE/.test(c)) return 'TABLE LAMP';
    return '';
}

function detectMounting(text) {
    /* Many datasheets list mounting as a CHOICE ("Recessed / Surface / Track").
       Picking one would be a guess, so when the sheet offers more than one
       style we leave MOUNTING blank and flag it for you. */
    const styles = [
        /recess/i, /surface[\s-]*(?:mount|\+|on\/off|dali|remote)/i,
        /suspend|pendant/i, /in-?ground|inground/i, /\btrack\b/i
    ].filter(re => re.test(text)).length;
    if (styles > 1) return '';
    if (/recess/i.test(text)) return 'RECESSED';
    if (/surface[\s-]*mount/i.test(text)) return 'SURFACE MOUNTED';
    if (/suspend|pendant/i.test(text)) return 'SUSPENDED';
    if (/in-?ground|inground/i.test(text)) return 'IN GROUND';
    if (/track/i.test(text)) return 'TRACK';
    if (/wall[\s-]*mount/i.test(text)) return 'SURFACE WALL';
    return '';
}

/* Driver: DALI, 1-10V, PHASE, 240V, 24V, 12V, 48V ... */
function detectDriver(text) {
    if (/\bDALI\b/i.test(text)) return 'DALI';
    if (/\b[01]\s*-\s*10\s*V\b/i.test(text)) return '1-10V';
    if (/\bphase[- ]?(?:cut|dim\w*|control)|\btriac\b|\btrailing[- ]edge|\bleading[- ]edge/i.test(text)) return 'PHASE DIMMABLE';
    if (/\b12\s*V\s*(DC)?\b/i.test(text)) return '12V';
    if (/\b24\s*V\s*(DC)?\b/i.test(text)) return '24V';
    if (/\b48\s*V\s*(DC)?\b/i.test(text)) return '48V';
    if (/\b(220\s*-\s*240|230|240)\s*V\b/i.test(text) || /mains/i.test(text)) return '240V';
    return '';
}

/* SDCM / MacAdam steps */
function detectSdcm(text) {
    const labelled = labelValue(text, 'sdcm', 34);
    if (labelled) {
        const bare = labelled.match(/^\s*([≤<]?)\s*(\d(?:\.\d)?)\s*(?:step|sdcm)?\s*$/i);
        if (bare) return (bare[1] ? '<' : '') + bare[2];
    }
    const scope = labelled || text;
    const m = scope.match(/SDCM\s*([≤<]?)\s*[:=]?\s*(\d(?:\.\d)?)/i)
        || scope.match(/(?:^|\s)([≤<]?)\s*(\d(?:\.\d)?)\s*(?:step)?\s*SDCM/i)
        || scope.match(/MacAdam\s*(?:steps?)?\s*([≤<]?)\s*[:=]?\s*(\d(?:\.\d)?)/i)
        || scope.match(/([≤<]?)\s*(\d(?:\.\d)?)\s*step\s*MacAdam/i);
    return m ? (m[1] ? '<' : '') + m[2] : '';
}

/* Lifetime in its many forms: L90B10 >55,000h / L80/B10 / L70 50000 hrs / L90 ... */
function detectLifetime(text) {
    const hit = labelValueLabelled(text, 'lifetime', 40);
    const scope = hit.value || text;

    /* "average life 35,000-50,000 hours" is a marketing range, not a rated lifetime.
       Without an L-code to qualify it there is nothing to schedule. */
    const isRange = /\d[\d,.]{2,}\s*[-–]\s*\d[\d,.]{2,}\s*h(?:rs|ours)?\b/i.test(scope);
    if (isRange && !/\bL\d{2,3}\b/i.test(scope)) return '';

    /* a labelled field is often just the hours - the L-code lives in the label,
       e.g. "TM21 L90 REPORTED LIFETIME [HRS]" or "L90   50,600hrs" */
    const bareHours = hit.value &&
        hit.value.match(/^\s*[>≥]?\s*([\d][\d,. ]{2,8})\s*(?:h(?:rs?|ours?)?)?\s*$/i);
    if (bareHours) {
        const n = bareHours[1].replace(/[ ,.]/g, '');
        if (+n >= 1000) {
            const tm21 = hit.label.match(/TM\s*-?\s*21\s*L(\d{2,3})/i);
            const lb2 = hit.label.match(/L(\d{2,3})\s*B(\d{2})/i);
            const lOnly2 = hit.label.match(/^L(\d{2,3})$/i);
            const code = tm21 ? 'TM21 L' + tm21[1]
                : (lb2 ? 'L' + lb2[1] + 'B' + lb2[2] : (lOnly2 ? 'L' + lOnly2[1] : ''));
            return [code, '>' + Number(n).toLocaleString('en-US') + 'h'].filter(Boolean).join('\n');
        }
    }

    /* prose form: "L70 (9K), B10 > 50,000 hours" / "Reported L70 B10 (10K) > 60,000 hrs" */
    const prose = scope.match(/\bL(\d{2,3})\s*(?:\([^)]*\))?\s*[,/]?\s*B(\d{2})\s*(?:\([^)]*\))?\s*[>≥]?\s*([\d][\d,.]{3,7})\s*h(?:rs|ours)?\b/i);
    if (prose) {
        const n = prose[3].replace(/[.,]/g, '');
        return 'L' + prose[1] + 'B' + prose[2] + '\n>' + Number(n).toLocaleString('en-US') + 'h';
    }

    /* label carries the code but the hours wrapped to a neighbouring line/column:
       "Lifetime L90B10 (hours)" ... "> 120,000" */
    const labelCode = hit.label && hit.label.match(/L(\d{2,3})\s*B(\d{2})/i);
    if (labelCode && !/\d{3,}/.test(hit.value || '')) {
        const lines = String(text).split('\n');
        const at = lines.findIndex(l => squash(l).includes(squash(hit.label)));
        if (at >= 0) {
            for (let k = at; k < Math.min(at + 3, lines.length); k++) {
                const h = lines[k].match(/[>≥]\s*([\d][\d,.]{3,9})/);
                if (h) {
                    const n = h[1].replace(/[.,]/g, '');
                    if (+n >= 1000) return 'L' + labelCode[1] + 'B' + labelCode[2] +
                        '\n>' + Number(n).toLocaleString('en-US') + 'h';
                }
            }
        }
    }

    const lb = scope.match(/\bL(\d{2,3})\s*[-–\/\s]{0,3}\s*B(\d{2})\b/i);
    const lOnly = lb ? null : scope.match(/\bL(70|80|90|100)\b/i);
    const hours = scope.match(/([\d][\d,.]{3,6})\s*(?:h(?:rs|ours)?|hr)\b/i);
    const code = lb ? 'L' + lb[1] + 'B' + lb[2] : (lOnly ? 'L' + lOnly[1] : '');
    if (!code && !hours) return '';
    const h = hours
        ? '>' + (/^\d+$/.test(hours[1]) ? Number(hours[1]).toLocaleString('en-US') : normThousands(hours[1])) + 'h'
        : '';
    return [code, h].filter(Boolean).join('\n');
}

/* Some manufacturers (iGuzzini) stack the headline specs as bare lines with the
   unit after the number and no label at all:
       34.7 W system
       3608 lm system
       3000 K
   A whole line consisting only of a number and a unit is unambiguous, so it is
   safe to read - unlike the same number found loose in a paragraph. */
function stackedValue(text, unitRe) {
    for (const line of String(text).split('\n')) {
        const v = line.trim();
        const m = v.match(unitRe);
        if (m) return m[1];
    }
    return '';
}

/* ---------- label-first field extractors ---------- */

function extractCct(text) {
    const v = labelValue(text, 'cct', 64, null, x => /[23456]\d{3}\s*°?\s*K|\b[23456][.,]\d\s*K/i.test(x));
    /* "3000K CRI80, 4000K CRI80" offers two colour temperatures - pick neither */
    if (v) {
        const all = [...new Set((v.match(/[23456]\d{3}\s*K/gi) || []).map(x => x.replace(/\s+/g, '')))];
        if (all.length > 1 && !/[-–]/.test(v)) return '';
    }
    let m = v && v.match(/([23456]\d{3})\s*[°]?\s*K?/);
    if (m) return m[1] + 'K';
    const stackK = stackedValue(text, /^([23456]\d{3})\s*K$/);
    if (stackK) return stackK + 'K';
    /* If the sheet publishes a CCT field we could not read, only stay silent when the
       document really is ambiguous (several different colour temperatures). A single
       consistent value elsewhere on the sheet is safe to use. */
    if (hasLabel(text, 'cct')) {
        const distinct = [...new Set((text.match(/\b[23456]\d{3}\s*°?\s*K\b/gi) || [])
            .map(x => x.replace(/[^\d]/g, '')))];
        if (distinct.length !== 1) return '';
    }
    /* tunable white: report the range rather than whichever end appears first */
    const range = text.match(/between\s+([23456]\d{3})\s*K?\s+and\s+([23456]\d{3})\s*K/i) ||
        text.match(/\b([23456]\d{3})\s*K\s*[-–]\s*([23456]\d{3})\s*K\b/);
    if (range) return range[1] + 'K-' + range[2] + 'K';
    m = text.match(/\b([23456]\d)(\d\d)\s*°?\s*K\b/) || text.match(/\b([23456]\d)(00|50)\s?K\b/);
    return m ? m[1] + m[2] + 'K' : '';
}

function extractLumens(text) {
    const v = labelValue(text, 'lumens', 64, null,
        x => /\d{2,6}\s*(lm|lumens)/i.test(x) || /^\s*\d{2,6}\s*$/.test(x));
    /* guard against efficacy ("63 lm/W") and per-channel RGBW tables */
    if (v && !/lm\s*\/\s*w/i.test(v) && !isOptionList(v) && !isNumericRange(v)) {
        const compound = /[A-Za-z]{3,}/.test(v.replace(/\b(lm|lumens|lumen)\b/gi, ''));
        const m = compound
            ? normDecimal(v).match(/(\d{2,6}(?:\.\d)?)\s*(?:lm|lumens)\s*(\/\s*m\b)?/i)
            : normDecimal(v).match(/(\d{2,6}(?:\.\d)?)\s*(?:lm|lumens)?\s*(\/\s*m\b)?/i);
        if (m) return tidyNum(m[1]) + 'lm' + (m[2] ? '/m' : '');
    }
    const stackLm = stackedValue(text, /^([\d]{2,6}(?:[.,]\d+)?)\s*lm(?:\s+system)?$/i);
    if (stackLm) return tidyNum(normDecimal(stackLm)) + 'lm';
    if (hasLabel(text, 'lumens')) return '';   // published but ambiguous - do not guess
    const m2 = text.match(/(\d{2,5})\s*(?:lm|lumens)\s*(\/\s*m\b)?(?!\s*\/\s*w)/i);
    return m2 ? m2[1] + 'lm' + (m2[2] ? '/m' : '') : '';
}

/* Prefer the LED power - that is what schedules quote. Falls back to system power. */
function extractWatts(text) {
    for (const key of ['ledWatts', 'watts']) {
        for (const label of (SPEC_LABELS[key] || [])) {
            /* A bare number is only a wattage when the LABEL names the unit
               ("WATTAGE [W]  10.8"). Under a loose label like "LED" it could be a
               lamp quantity or part-number fragment. */
            const unitInLabel = /watt|\[w\]|power/i.test(label);
            const v = labelValue(text, key, 30, label, x =>
                /\d\s*W\b|\d\s*W\s*\//i.test(x) ||
                (unitInLabel && /^\s*\d+([.,]\d+)?\s*$/.test(x)));
            if (!v || isOptionList(v) || isNumericRange(v)) continue;
            /* "3 x 10W" - several modules. Report it verbatim, never one module. */
            const mult = normDecimal(v).match(/(\d{1,2})\s*[x×]\s*(\d{1,4}(?:\.\d{1,2})?)\s*W\b/i);
            if (mult) return mult[1] === '1' ? tidyNum(mult[2]) + 'W'
                : mult[1] + ' x ' + tidyNum(mult[2]) + 'W';
            /* "13W", "15W p/m", "10.8W/m" - keep per-metre notation */
            let m = normDecimal(v).match(/(\d{1,4}(?:\.\d{1,2})?)\s*W\s*(p?\s*\/?\s*m\b)?/i);
            if (!m && unitInLabel) m = normDecimal(v).match(/^\s*(\d{1,4}(?:\.\d{1,2})?)\s*$/);
            if (m) return tidyNum(m[1]) + 'W' + (m[2] ? '/m' : '');
        }
    }
    const stackW = stackedValue(text, /^([\d]{1,4}(?:[.,]\d+)?)\s*W(?:\s+system)?$/i);
    if (stackW) return tidyNum(normDecimal(stackW)) + 'W';
    if (hasLabel(text, 'watts') || hasLabel(text, 'ledWatts')) return '';
    const m = normDecimal(text).match(/(?:^|[\s(:])(\d{1,3}(?:\.\d{1,2})?)\s*W\b/);
    return m ? tidyNum(m[1]) + 'W' : '';
}

/* Medical examination lights are specified by illuminance at a working distance
   ("83,300 lux @ 600mm") rather than by lumens. Returns the closest-distance
   figure, quoted exactly as printed. */
function extractIlluminance(text) {
    const scope = labelValue(text, 'illuminance', 90) || text;
    const hits = [...scope.matchAll(/([\d][\d,. ]{2,9})\s*lux\s*@?\s*(\d{3,4})\s*mm/gi)]
        .map(m => ({ lux: m[1].replace(/[ .]/g, '').replace(/,$/, ''), at: +m[2] }))
        .filter(h => /\d/.test(h.lux));
    if (!hits.length) return '';
    hits.sort((a, b) => a.at - b.at);
    return hits[0].lux + ' lux @ ' + hits[0].at + 'mm';
}

function extractCri(text) {
    const v = labelValue(text, 'cri', 24, null, x =>
        /^(cri|ra)?\s*[>≥]?\s*\d{2}\s*\+?\.?$/i.test(x.trim()) ||
        /\b(cri|ra)\s*[>≥]?\s*\d{2}(?!\d)\b/i.test(x));
    /* Report exactly what is claimed: ">90", "90+" or a bare "92" - never invent a
       "+". Prefer the number adjacent to "CRI"/"Ra": a combined field reading
       "3000K CRI80" must not yield 30. */
    let m = v && (v.match(/(?:cri|ra)\s*(>|≥|>=)?\s*(\d{2})(?!\d)\s*(\+)?/i)
        || v.match(/(>|≥|>=)?\s*(\d{2})(?!\d)\s*(\+)?/));
    if (m) {
        /* several CRI values offered ("3000K CRI80, 4000K CRI90") is ambiguous */
        const all = [...new Set((v.match(/(?:cri|ra)\s*[>≥]?\s*(\d{2})(?!\d)/gi) || [])
            .map(x => x.replace(/\D/g, '')))];
        if (all.length > 1) return '';
        return (m[1] ? '>' : '') + m[2] + (m[3] ? '+' : '');
    }
    /* no hasLabel guard: the fallback demands a literal "CRI"/"Ra" beside the number */
    /* (?!\d) stops "CCT / CRI  3000K" being read as CRI 30 */
    m = text.match(/CRI\s*(>|≥)?\s*[:=]?\s*(\d{2})(?!\d)\s*(\+)?/i) ||
        text.match(/()(\d{2})(?!\d)\s*CRI\b()/i) ||
        text.match(/\bR[aA]\s*(>|≥)?\s*[:=]+\s*(\d{2})(?!\d)\s*(\+)?/);
    return m ? (m[1] ? '>' : '') + m[2] + (m[3] ? '+' : '') : '';
}

function extractBeam(text) {
    const v = labelValue(text, 'beam', 24, null, x => /\d{1,3}\s*°/.test(x));
    const m = v && v.match(/(\d{1,3})\s*°/);
    if (m) return m[1] + '°';
    /* only trust free text when written as degrees, or "Wide beam 4000K" reads as 400° */
    const m2 = text.match(/beam\s*(?:angle|width|spread)?\s*[:=]?\s*(\d{1,3})\s*(?:°|deg)/i);
    return m2 ? m2[1] + '°' : '';
}

function extractIp(text) {
    /* the label often carries the "IP", leaving a bare number: "IP Rating   44" */
    const v = labelValue(text, 'ip', 20, null,
        x => /IP\s?\d{2}/i.test(x) || /^\s*\d{2}\s*$/.test(x));
    let m = v && (v.match(/IP\s?(\d{2})/i) || v.match(/^\s*(\d{2})\s*$/));
    if (m) return 'IP' + m[1];
    m = text.match(/\bIP\s?(\d{2})\b/i);
    return m ? 'IP' + m[1] : '';
}

/* A finish is a colour or material phrase - never a measurement, an optic or a
   fragment of a spec line ("W system", "TED 210x144mm"). */
function looksLikeFinish(v) {
    const t = String(v).trim();
    if (!t || t.length < 3 || t.length > 34) return false;
    if (/\d/.test(t)) return false;                       // no measurements or codes
    if (/\b(system|optic|beam|led|mount|lumen|watt|driver|class|ip\d)\b/i.test(t)) return false;
    return /^[A-Za-z][A-Za-z \-\/&,()]+$/.test(t);
}

/* Many sheets title themselves "Family / CODE Finish" (iGuzzini: "iPro / BK32.01
   White", "View / P014.47 White / Black"). That line is the most reliable source of
   the product name, its order code and its finish. */
function titleLineParts(text) {
    const lines = String(text).split('\n').map(l => l.trim()).filter(Boolean).slice(0, 6);
    let m = null;
    for (const line of lines) {
        m = line.match(/^(.{2,40}?)\s*\/\s*([A-Z]{1,4}\d{1,4}[.\-][A-Z0-9]{1,4})\s*(.*)$/);
        if (m) break;
    }
    /* Second layout used by the same manufacturers: the product name sits on its
       own line and the order code heads the line below it -
           Laser Blade XS
           LBXS-004930 - White body Black optic Standard no cable
       Without this the code was read as the name. */
    if (!m) {
        for (let i = 1; i < lines.length; i++) {
            const below = lines[i].match(/^([A-Z]{2,6}[-.][A-Z0-9]{3,10})\s*[-–]\s*(.+)$/);
            if (!below) continue;
            const above = lines[i - 1];
            if (!/^[A-Za-z][A-Za-z0-9 .&'\-]{1,39}$/.test(above)) continue;
            if (/^(description|part of|code|reference)\b/i.test(above)) continue;
            return { name: above.trim(), code: below[1].trim(),
                     finish: (below[2].match(/^([A-Za-z ]+?)\s+body\b/i) || [])[1] || '' };
        }
    }
    if (!m) return null;
    /* 'Black - Black - EN' -> 'Black'; drop the language suffix and any repeat */
    const finish = stripLanguageSuffix((m[3] || '').replace(/\s*\+.*$/, ''))
        .split(/\s+[-\/]\s+/)[0].trim();
    return { name: m[1].trim(), code: m[2].trim(), finish };
}

function extractFinish(text) {
    let v = labelValue(text, 'finish', 40, null, x => looksLikeFinish(x));
    if (!v) {
        const t = titleLineParts(text);
        return (t && looksLikeFinish(t.finish)) ? t.finish : '';
    }
    v = v.split(/\s{2,}|\s+RAL\b|,/)[0].trim();
    /* drop trailing junk like a RAL number that ran on */
    v = v.replace(/\b\d{4}\b.*$/, '').trim();
    return v.length > 1 && v.length < 34 && /[a-z]/i.test(v) ? v : '';
}

/* Manufacturer "Category"/"Installation" field -> our MOUNTING column */
function categoryToMounting(cat) {
    /* a real category is a short phrase; a sentence means we matched prose */
    if (!cat || cat.length > 34 || /[;.]/.test(cat)) return '';
    const c = cat.toUpperCase();
    if (/PLASTER|SANDWICH|PLASTERBOARD/.test(c)) return 'RECESSED';
    if (/T-?BAR|GRID/.test(c) && /RECESS/.test(c)) return 'RECESSED';
    if (/CEILING\s*RECESS|RECESSED\s*CEILING/.test(c)) return 'RECESSED';
    if (/WALL\s*RECESS/.test(c)) return 'WALL RECESSED';
    if (/FLOOR\s*RECESS|IN[\s-]?GROUND/.test(c)) return 'IN GROUND';
    if (/RECESS/.test(c)) return 'RECESSED';
    if (/SURFACE/.test(c)) return 'SURFACE MOUNTED';
    if (/SUSPEND|PENDANT/.test(c)) return 'SUSPENDED';
    if (/TRACK/.test(c)) return 'TRACK';
    if (/^WALL\b/.test(c)) return 'SURFACE WALL';
    if (/PORTABLE|TABLE/.test(c)) return 'PORTABLE';
    return '';
}

/* DRIVER carries the supply/dimming type: DALI, PUSH, 1-10V, phase, or 240V
   when the fitting is not dimmable. CONTROL is a design decision, never scanned. */
function extractDriver(text) {
    const v = labelValue(text, 'dimming', 70, null, x =>
        /dali|dmx|push|phase|mains|no\s*dim|non[- ]?dim|10\s*v|bluetooth|casambi|zigbee|switch/i.test(x));

    /* A control field that lists every option the range supports - or that the sheet
       publishes but leaves ambiguous - says nothing about THIS fitting. Fall back to
       the supply voltage, which is a fact, and never to prose. */
    if ((v && isOptionList(v)) || (!v && hasLabel(text, 'dimming'))) {
        const volt = labelValue(text, 'voltage', 24, null, x => /\d{2,3}\s*V/i.test(x));
        const mv = volt && volt.match(/(\d{2,3})\s*V/i);
        return mv ? mv[1] + 'V' : '';
    }
    const src = (v || text).toUpperCase();
    const parts = [];
    if (/\bDALI\b/.test(src)) parts.push('DALI');
    if (/\bDMX\b/.test(src)) parts.push('DMX');
    if (/\bPUSH\b/.test(src)) parts.push('PUSH');
    if (/\b[01]\s*-\s*10\s*V\b/.test(src)) parts.push('1-10V');
    /* "PHASE" must mean dimming - not "the main phases" in a manufacturing paragraph */
    if (/\bTRIAC\b|\bPHASE[- ]?(?:CUT|DIM\w*|CONTROL)|\bTRAILING[- ]EDGE|\bLEADING[- ]EDGE|\bMAINS\s*DIM/.test(src))
        parts.push('PHASE DIMMABLE');
    if (parts.length) return parts.join(' / ');
    if (/\bNO\s*DIM\b|NON[- ]?DIM|NOT DIMMABLE/.test(src)) return '240V';
    return detectDriver(text);
}

/* Dimensions in common datasheet forms */
/* Only ever the fitting's own size - never a cut-out, never packaging.
   Round fittings read "89mm(DIA) x 74mm(H)". Anything incomplete is left blank
   so the cell stays flagged rather than half-answered. */
function detectDimensions(text) {
    let m;
    /* inline summary form used in product headlines: "L:1194mm W:293mm H:60mm" */
    const inl = text.match(/\bL\s*:\s*(\d{1,5}(?:[.,]\d)?)\s*mm\s+W\s*:\s*(\d{1,5}(?:[.,]\d)?)\s*mm\s+H\s*:\s*(\d{1,5}(?:[.,]\d)?)\s*mm/i);
    if (inl) return `${normDecimal(inl[1])}mm(L) x ${normDecimal(inl[2])}mm(W) x ${normDecimal(inl[3])}mm(H)`;
    const inlWH = !inl && text.match(/\bW\s*:\s*(\d{1,5}(?:[.,]\d)?)\s*mm\s+H\s*:\s*(\d{1,5}(?:[.,]\d)?)\s*mm/i);
    if (inlWH) return `${normDecimal(inlWH[1])}mm(DIA) x ${normDecimal(inlWH[2])}mm(H)`;

    /* explicit L / W / H fields (Eagle-style technical overview) */
    /* Some sheets quote metres ("Luminaire Width: (m) 0.093"), so a small decimal
       value is converted to millimetres. */
    const num = (k) => {
        const v = labelValue(text, k, 20);
        const mm = v && v.match(/^\s*(\d{1,5}(?:[.,]\d{1,4})?)\s*(mm|cm|m)?\s*$/i);
        if (!mm) return '';
        const rawN = normDecimal(mm[1]);
        const n = parseFloat(rawN);
        const isMetres = /^m$/i.test(mm[2] || '') || (/\./.test(rawN) && n < 10);
        return isMetres ? String(Math.round(n * 1000)) : rawN;
    };
    /* An explicit "Diameter  Ø89mm" beats a generic L/W/H, which on some sheets
       belongs to the remote driver rather than the luminaire. */
    const diaExplicit = labelValue(text, 'diameter', 24, null, x => /[Ø⌀ø]/.test(x));
    const hgtForDia = labelValue(text, 'height', 24, null, x => /\d\s*mm/i.test(x));
    if (diaExplicit && hgtForDia) {
        const dN = diaExplicit.match(/(\d{2,4}(?:[.,]\d)?)/);
        const hN = hgtForDia.match(/(\d{2,4}(?:[.,]\d)?)/);
        if (dN && hN) return `${normDecimal(dN[1])}mm(DIA) x ${normDecimal(hN[1])}mm(H)`;
    }

    const Lv = num('length'), Wv = num('diameter'), Hv = num('height');
    /* only call it a diameter if the sheet actually says so - "Luminaire Width"
       on a linear profile is a width */
    const round = /\b(diameter|dia\b|round|[Ø⌀])/i.test(text);
    if (Lv && Wv && Hv) return `${Lv}mm(L) x ${Wv}mm(W) x ${Hv}mm(H)`;
    if (!Lv && Wv && Hv) return `${Wv}mm(${round ? 'DIA' : 'W'}) x ${Hv}mm(H)`;

    /* separate Diameter + Height fields are the norm for downlights */
    const diaV = labelValue(text, 'diameter', 24);
    const hgtV = labelValue(text, 'height', 24);
    const diaN = diaV && diaV.match(/[ØøΦφ⌀]?\s?(\d{2,4}(?:[.,]\d)?)\s*mm/i);
    const hgtN = hgtV && hgtV.match(/(\d{2,4}(?:[.,]\d)?)\s*mm/i);
    if (diaN && hgtN) return `${normDecimal(diaN[1])}mm(DIA) x ${normDecimal(hgtN[1])}mm(H)`;

    /* a labelled product-dimensions field wins, and never packaging */
    const labelled = labelValue(text, 'dims', 90);
    /* dimensions quoted for several variants are ambiguous - leave blank and flag */
    if (labelled && !hasVariants(labelled)) {
        const wh = labelled.match(/(\d{1,4}(?:[.,]\d)?)\s*mm\s*\(?\s*(?:w|width)\b[^)]*\)?[,\s]+(\d{1,4}(?:[.,]\d)?)\s*mm\s*\(?\s*(?:h|height)\b/i);
        if (wh) return `${normDecimal(wh[1])}mm(W) x ${normDecimal(wh[2])}mm(H)`;
        const dh = labelled.match(/(\d{1,4}(?:[.,]\d)?)\s*mm\s*\(?\s*(?:dia|diameter|Ø)\b[^)]*\)?[,\s]+(?:x\s*)?(\d{1,4}(?:[.,]\d)?)\s*mm\s*\(?\s*(?:l|length|h|height)\b/i);
        if (dh) return `${normDecimal(dh[1])}mm(DIA) x ${normDecimal(dh[2])}mm(H)`;
        /* "66mm (trim diameter), 53mm (body diameter), 98mm (height)" - the visible
           trim diameter and the overall height are what a schedule needs */
        const trim = labelled.match(/(\d{1,4}(?:[.,]\d)?)\s*mm\s*\([^)]*diameter[^)]*\)/i);
        const hh = labelled.match(/(\d{1,4}(?:[.,]\d)?)\s*mm\s*\([^)]*height[^)]*\)/i);
        if (trim && hh) return `${normDecimal(trim[1])}mm(DIA) x ${normDecimal(hh[1])}mm(H)`;
    }
    if (labelled && !hasVariants(labelled)) {
        const d = labelled.match(/[ØøΦφ⌀]\s?(\d{2,4}(?:[.,]\d)?)\s*(?:mm)?\s*[x×*]\s*[HWDhwd]?\s*(\d{2,4}(?:[.,]\d)?)\s*mm/i);
        if (d) return `${normDecimal(d[1])}mm(DIA) x ${normDecimal(d[2])}mm(H)`;
        const t = labelled.match(/(\d{2,4}(?:[.,]\d)?)\s*[x×*]\s*(\d{2,4}(?:[.,]\d)?)(?:\s*[x×*]\s*(\d{2,4}(?:[.,]\d)?))?\s*mm/i);
        if (t) return t[3]
            ? `${normDecimal(t[1])}mm(L) x ${normDecimal(t[2])}mm(W) x ${normDecimal(t[3])}mm(H)`
            : `${normDecimal(t[1])}mm(W) x ${normDecimal(t[2])}mm(H)`;
    }
    /* prose forms on brochure sheets: "89mm diameter x 200-235mm in height",
       "100mm round, 80mm high", "70 wide x 75 high" */
    const proseDia = text.match(/(\d{2,4}(?:\.\d)?)\s*mm\s*(?:diameter|dia\b|round)\s*[x×,]\s*(\d{2,4}(?:-\d{2,4})?(?:\.\d)?)\s*(?:mm)?\s*(?:in\s+)?(?:height|high|deep|depth)/i);
    if (proseDia) return `${proseDia[1]}mm(DIA) x ${proseDia[2]}mm(H)`;
    const proseWH = text.match(/(\d{2,4}(?:\.\d)?)\s*(?:mm)?\s*wide\s*[x×,]\s*(\d{2,4}(?:\.\d)?)\s*(?:mm)?\s*high/i);
    if (proseWH) return `${proseWH[1]}mm(W) x ${proseWH[2]}mm(H)`;

    /* remove any line describing something that is NOT the fitting's own size:
       packaging, cut-outs, bend radii. These otherwise masquerade as dimensions. */
    text = text.split('\n')
        .filter(line => !/(packag\w*|carton|box|shipping|pallet|recess measurement|recess dimension|cut[\s-]?out|cutout|aperture|bend|radius)/i.test(line))
        .join('\n');
    // Ø89 x 100mm  /  Ø 89mm x H 100mm
    m = text.match(/[ØøΦφ⌀]\s?(\d{2,4}(?:\.\d)?)\s*(?:mm)?\s*[x×*]\s*(?:H\s*[:.]?\s*)?(\d{2,4}(?:\.\d)?)\s*mm/i);
    if (m) return `${m[1]}mm(DIA) x ${m[2]}mm(H)`;
    // DIA/diameter 89mm ... height 100mm
    const dia = text.match(/(?:dia(?:meter)?)\s*[:.]?\s*(\d{2,4}(?:\.\d)?)\s*mm/i);
    const hgt = text.match(/(?:height|\bH\b)\s*[:.]?\s*(\d{2,4}(?:\.\d)?)\s*mm/i);
    if (dia && hgt) return `${dia[1]}mm(DIA) x ${hgt[1]}mm(H)`;
    // 100 x 60 x 35 mm  (mm only at the end)
    m = text.match(/(\d{2,4}(?:\.\d)?)\s*[x×*]\s*(\d{2,4}(?:\.\d)?)\s*[x×*]\s*(\d{2,4}(?:\.\d)?)\s*mm/i);
    if (m) return `${m[1]}mm(L) x ${m[2]}mm(W) x ${m[3]}mm(H)`;
    // 100mm x 60mm x 35mm
    m = text.match(/(\d{2,4}(?:\.\d)?)\s?mm\s*[x×*]\s*(\d{2,4}(?:\.\d)?)\s?mm(?:\s*[x×*]\s*(\d{2,4}(?:\.\d)?)\s?mm)?/i);
    if (m) return m[3] ? `${m[1]}mm(L) x ${m[2]}mm(W) x ${m[3]}mm(H)` : `${m[1]}mm(W) x ${m[2]}mm(H)`;
    // 100 x 60 mm
    m = text.match(/(\d{2,4}(?:\.\d)?)\s*[x×*]\s*(\d{2,4}(?:\.\d)?)\s*mm/i);
    if (m) return `${m[1]}mm(W) x ${m[2]}mm(H)`;
    // W 100mm ... H 60mm ... D 35mm
    const w = text.match(/\bW\s*[:.]?\s*(\d{2,4}(?:\.\d)?)\s*mm/i);
    const h2 = text.match(/\bH\s*[:.]?\s*(\d{2,4}(?:\.\d)?)\s*mm/i);
    const dpt = text.match(/\bD\s*[:.]?\s*(\d{2,4}(?:\.\d)?)\s*mm/i);
    if (w && h2) return dpt
        ? `${w[1]}mm(W) x ${h2[1]}mm(H) x ${dpt[1]}mm(D)`
        : `${w[1]}mm(W) x ${h2[1]}mm(H)`;
    return '';
}

/* ==================== IES PARSER (LM-63) ==================== */

const IES = {
    parse(text) {
        const kw = {};
        const kwRe = /\[([\w_]+)\][ \t]*(.*)/g;
        let m;
        while ((m = kwRe.exec(text)) !== null) {
            const key = m[1].toUpperCase();
            const val = m[2].trim();
            if (kw[key] !== undefined && val) kw[key] += ' ' + val;
            else if (kw[key] === undefined) kw[key] = val;
        }

        const tiltMatch = text.match(/TILT\s*=\s*(\S+)/);
        if (!tiltMatch) throw new Error('Not a valid IES file (no TILT line)');
        let nums = (text.slice(tiltMatch.index + tiltMatch[0].length)
            .match(/-?\d+\.?\d*(?:[eE][-+]?\d+)?/g) || []).map(Number);
        if (tiltMatch[1].toUpperCase() !== 'NONE') {
            const nPairs = nums[1];
            nums = nums.slice(2 + 2 * nPairs);
        }
        if (nums.length < 13) throw new Error('IES file truncated');

        const [nLamps, lumensPerLamp, multiplier, nV, nH] = nums.slice(0, 5);
        const [ballastFactor, , inputWatts] = nums.slice(10, 13);
        let i = 13;
        const V = nums.slice(i, i + nV); i += nV;
        const H = nums.slice(i, i + nH); i += nH;
        const planes = [];
        for (let h = 0; h < nH; h++) {
            planes.push(nums.slice(i, i + nV).map(c => c * multiplier * ballastFactor));
            i += nV;
        }
        if (planes.length !== nH || planes[nH - 1].length !== nV) throw new Error('IES candela data truncated');
        return { keywords: kw, nLamps, lumensPerLamp, inputWatts, V, H, planes };
    },

    peak(d) {
        let imax = -Infinity, ph = 0, pv = 0;
        d.planes.forEach((plane, hi) => plane.forEach((val, vi) => {
            if (val > imax) { imax = val; ph = hi; pv = vi; }
        }));
        return { imax, ph, pv };
    },

    beamAngle(d, frac) {
        const { imax, ph, pv } = this.peak(d);
        if (imax <= 0) return null;
        const plane = d.planes[ph], V = d.V, thr = imax * frac;
        const cross = (dir) => {
            let idx = pv;
            while (idx + dir >= 0 && idx + dir < V.length) {
                const a = plane[idx], b = plane[idx + dir];
                if (a >= thr && b < thr) return V[idx] + (a - thr) / (a - b) * (V[idx + dir] - V[idx]);
                idx += dir;
            }
            return null;
        };
        let lo = cross(-1), hi = cross(1);
        const peakAngle = V[pv];
        const nearAxis = (b) => (b === 0 || b === 180) && Math.abs(peakAngle - b) <= 5;
        if (lo === null) lo = nearAxis(V[0]) && hi !== null ? peakAngle - (hi - peakAngle) : V[0];
        if (hi === null) hi = nearAxis(V[V.length - 1]) && lo !== null ? peakAngle + (peakAngle - lo) : V[V.length - 1];
        return Math.abs(hi - lo);
    },

    totalFlux(d) {
        const { V, H, planes } = d;
        const avg = V.map((_, v) => H.reduce((s, _h, h) => s + planes[h][v], 0) / H.length);
        let F = 0;
        for (let k = 0; k < V.length - 1; k++) {
            const t1 = V[k] * Math.PI / 180, t2 = V[k + 1] * Math.PI / 180;
            F += ((avg[k] + avg[k + 1]) / 2) * 2 * Math.PI * (Math.cos(t1) - Math.cos(t2));
        }
        return Math.abs(F);
    },

    summarise(d) {
        const kw = d.keywords;
        const allText = Object.entries(kw).map(([k, v]) => k + ' ' + v).join(' ');

        let cct = kw.CCT ? kw.CCT.replace(/\D/g, '') : null;
        if (!cct) { const m = allText.match(/\b([23456]\d)(00|50)\s*K\b/i); if (m) cct = m[1] + m[2]; }

        let cri = kw.CRI ? kw.CRI.replace(/\D/g, '') : null;
        if (!cri) {
            const m = allText.match(/CRI\s*[:=]?\s*(\d{2})/i) || allText.match(/(\d{2})\s*CRI/i)
                || allText.match(/IRC\s*=\s*\S*\/(\d{2})/i);
            if (m) cri = m[1];
        }

        const watts = d.inputWatts > 0 ? Math.round(d.inputWatts * 10) / 10 : null;
        let lumens;
        const absKw = kw._ABSOLUTELUMENS && parseFloat(kw._ABSOLUTELUMENS);
        if (d.lumensPerLamp < 0) lumens = absKw || Math.round(this.totalFlux(d));
        else lumens = Math.round(d.lumensPerLamp * d.nLamps);

        const beam = this.beamAngle(d, 0.5);
        const field = this.beamAngle(d, 0.1);

        return {
            manufacturer: kw.MANUFAC || '',
            luminaire: kw.LUMINAIRE || '',
            code: kw.LUMCAT || '',
            cct: cct ? cct + 'K' : '',
            cri: cri || '',
            watts, lumens,
            beam: beam !== null ? Math.round(beam) : null,
            field: field !== null ? Math.round(field) : null,
            efficacy: watts ? Math.round(lumens / watts) : null
        };
    }
};

/* ==================== XLSX EXPORT ==================== */

function buildWorkbook(ExcelJSLib, sched) {
    const hidden = sched.hiddenCols || {};
    const XCOLS = COLS.filter(c => !hidden[c.key]);

    const wb = new ExcelJSLib.Workbook();
    const ws = wb.addWorksheet('LFS');
    const AN = 'Arial Narrow';
    const thin = { style: 'thin' };
    const allBorders = { top: thin, left: thin, bottom: thin, right: thin };

    XCOLS.forEach((c, i) => { ws.getColumn(i + 1).width = c.xw; });

    ws.mergeCells(1, 1, 1, XCOLS.length);
    const title = ws.getCell(1, 1);
    title.value = sched.title || 'LIGHT FITTING SCHEDULE';
    title.font = { name: AN, size: 20, bold: true };
    title.alignment = { horizontal: 'center', vertical: 'middle' };
    ws.getRow(1).height = 30;

    const hr = ws.getRow(2);
    XCOLS.forEach((c, i) => {
        const cell = hr.getCell(i + 1);
        cell.value = c.label;
        cell.font = { name: AN, size: 14, bold: true };
        cell.alignment = { horizontal: 'center', vertical: 'middle' };
        cell.border = allBorders;
    });
    hr.height = 25;

    sched.rows.filter(row => !row.hidden).forEach((row, ri) => {
        const r = ws.getRow(3 + ri);
        r.height = 52.5;
        XCOLS.forEach((c, ci) => {
            const cell = r.getCell(ci + 1);
            const raw = (row.cells[c.key] || '').trim();
            const baseFont = { name: AN, size: 10, bold: c.key === 'tag' };
            const rich = raw ? mdToRich(raw, baseFont) : null;
            cell.value = rich || (stripMd(raw) || '-');
            cell.font = baseFont;
            cell.alignment = { horizontal: 'center', vertical: 'middle', wrapText: true };
            cell.border = allBorders;
        });
    });

    return wb;
}

/* ==================== SCAN LOGIC ==================== */

function blankRow() {
    const cells = {};
    COLS.forEach(c => { cells[c.key] = ''; });
    return {
        id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
        cells, ies: null, scanned: false, loading: null
    };
}

function shorten(s, n) { return s.length > n ? s.slice(0, n - 1) + '…' : s; }

/* Datasheet file names often carry a language or export marker: "... - EN",
   "..._en", "-en-specs". None of that belongs in the product name. */
function stripLanguageSuffix(s) {
    return String(s || '')
        .replace(/[\s_\-]+(en|de|fr|es|it|nl|pt|zh)([\s_\-]*(specs?|spec\s*sheet))?\s*$/i, '')
        .replace(/[\s_\-]+$/, '')
        .trim();
}

/* MANUFACTURER / MODEL cell:  **PRODUCT NAME**  \n  MANUFACTURER  \n  **CODE:** XXX */
/* Strip the trailing options a manufacturer's "Name" field carries, e.g.
   "DIVI INDIRECT END 3000K NT" -> "DIVI INDIRECT END". CCT lives in LIGHT
   SOURCE and the finish letters in FINISH, so they are noise here. */
/* Words that are headings on a datasheet, never the name of a fitting.
   These leaked in when a label sat directly above the value we wanted. */
const NOT_A_NAME = /^(DESCRIPTION|LOCATION|REFERENCE|NAME|CODE|TYPE|FINISH|COLOUR|COLOR|MOUNTING|DIMENSIONS|GENERAL|NOTES|OPTIONS|ACCESSORIES|SPECIFICATIONS?|SPECSHEETS?|PRODUCT|MODEL|SERIES|RANGE|FAMILY|PART|ITEM|DETAILS|DATA|IMAGE|PHOTOMETRY|DOWNLIGHT|LUMINAIRE|FIXTURE)$/i;

function cleanProductName(s) {
    return String(s || '')
        .replace(/\s+\d{3,5}\s?K(\s+[A-Z]{1,3})?$/i, '')
        .replace(/\s*[-_]\s*$/, '')
        .trim();
}

/* Is this a plausible PRODUCT NAME, or did we just pick up an order code?
   Blake's rule: if we are not confident, leave it out. A blank name with the
   manufacturer and code still filled in is useful; "LBXS-004930WHITEBLACK" is
   not. Judged per word, so "CAPRI 110" and "PLEIAD G4 125" survive while
   "LBXS-004930" and "LSEVO-AAH66Y" do not. */
function looksLikeProductName(s) {
    const v = cleanProductName(s);
    if (v.length < 2 || v.length > 40) return false;
    if (/_/.test(v)) return false;                       // SD_SpecSheets_Isle
    /* a datasheet heading is not a product name */
    if (NOT_A_NAME.test(v)) return false;
    const words = v.split(/\s+/);
    if (words.length > 6) return false;
    /* a lone short token is almost always a code prefix ("EDB"), not a name */
    if (words.length === 1 && v.length < 4) return false;
    const codeish = words.some(w =>
        /\d{4,}/.test(w) ||                    // 004930, 73013
        (/[-._\/]/.test(w) && /\d/.test(w)) || // LBXS-004930, 312392.004
        /[A-Za-z]{3,}\d{2,}/.test(w) ||        // AAH66Y
        /\d{2,}[A-Za-z]{2,}/.test(w)           // 66YBLACK
    );
    if (codeish) return false;
    /* a real name has at least one pronounceable word */
    return words.some(w => /[aeiouy]/i.test(w) && w.length >= 3);
}

/* Some suppliers put the product name in the filename, in one of two shapes:
       "AURASP-0900DD-2 - Aura - Versalux Lighting Systems"
       "2217-POL-P-BD-L_Biconica Pol RGB"
   Only used when the sheet itself did not name the product, and every
   candidate still has to pass looksLikeProductName(). */
function nameFromFilename(stem, supplier) {
    const stripCode = x => String(x).replace(/^[A-Za-z0-9]+(?:[-._][A-Za-z0-9]+)+\s*/, '').trim();
    /* strip document words and a trailing order code before we look */
    const clean = String(stem)
        .replace(/\b(cut|data|spec(?:ification)?s?)[\s+_-]*sheet\b/ig, '')
        .replace(/[-_+]\d{4,}\b/g, '')
        .replace(/[\s+_-]+$/, '').trim();
    const dash = String(stem).split(/\s+-\s+/);
    const und = String(stem).split(/\s*_\s*/);
    const cands = [];
    /* "Compact (CMP-017-RES-STD-W2790)" and "Icon (ICN-REC-W2790)" */
    const paren = String(stem).match(/^([A-Za-z][A-Za-z0-9 &'.\-]{1,34}?)\s*\(/);
    if (paren) cands.push(paren[1]);
    if (clean && clean !== stem) cands.push(clean);
    if (dash.length >= 3) cands.push(dash[1]);
    if (und.length >= 2) { cands.push(stripCode(und[0])); cands.push(und[1]); }
    if (dash.length === 2) cands.push(stripCode(dash[0]));
    const sup = (supplier || '').toUpperCase();
    for (const c of cands) {
        const v = String(c || '').trim();
        if (!v) continue;
        const V = v.toUpperCase();
        /* never let the manufacturer's own name become the product name */
        if (sup && (sup.includes(V) || V.includes(sup.split(' ')[0]))) continue;
        if (SUPPLIERS.some(x => V.includes(x) || x.includes(V))) continue;
        /* filenames are full of words that are not product names */
        if (/\b(DATA|DATASHEET|SHEET|SPEC|SPECS|CUT|PRODUCT|REF|COPY|FINAL|REV|EN)\b/.test(V)) continue;
        if (looksLikeProductName(v)) return v;
    }
    return '';
}

function modelCell(product, manufacturer, code) {
    /* Manufacturer "Name" fields often append the ordered options, e.g.
       "DIVI INDIRECT END 3000K NT". Colour temperature lives in LIGHT SOURCE
       and the finish letters live in FINISH, so drop them from the name
       rather than repeating them here. */
    product = String(product || '').replace(/\s+\d{3,5}\s?K(\s+[A-Z]{1,3})?$/i, '').trim();
    return [
        product ? '**' + scheduleCase(product) + '**' : '',
        manufacturer ? manufacturer.toUpperCase() : '',
        code ? '**CODE:** ' + code : ''
    ].filter(Boolean).join('\n');
}

/* Extract LFS cell values from an IES file (fills only blank cells) */
function iesIntoRow(row, name, text) {
    const d = IES.parse(text);
    const s = IES.summarise(d);
    const allText = Object.entries(d.keywords).map(([k, v]) => k + ' ' + v).join(' ');
    const filled = [];
    const fill = (key, val) => {
        /* one place where every scanned value is normalised to schedule case:
           CAPS, but mm / lm / h / lm/W stay lowercase */
        if (val && !(row.cells[key] || '').trim()) { row.cells[key] = scheduleCase(val); filled.push(key); }
    };

    fill('source', [s.cct, s.watts ? s.watts + 'W' : '', s.lumens ? s.lumens + 'lm' : '']
        .filter(Boolean).join('\n'));
    fill('cri', s.cri);
    fill('description', detectDescription(allText));
    fill('mounting', detectMounting(allText));
    fill('driver', detectDriver(allText));
    fill('ip', (allText.match(/\bIP\s?(\d{2})\b/i) || [])[1] ? 'IP' + allText.match(/\bIP\s?(\d{2})\b/i)[1] : null);
    fill('model', modelCell(s.luminaire ? shorten(s.luminaire, 60) : '',
        s.manufacturer || detectSupplier(allText), s.code));

    row.ies = { name, beam: s.beam, field: s.field, lumens: s.lumens, watts: s.watts, efficacy: s.efficacy };

    const supplier = s.manufacturer || detectSupplier(allText);
    for (const c of COLS) {
        const fix = Learning.correctionFor(supplier, c.key, row.cells[c.key]);
        if (fix) row.cells[c.key] = fix;
    }
    FileStore.putText(row.id, allText.slice(0, 200000)).catch(() => { });
    row.scan = { supplier, cells: { ...row.cells } };
    return filled;
}

/* Brochure sheets put the standard specification in a left column and an "Options"
   column beside it. The options are what you COULD order, not what this fitting is,
   so that column is removed before extraction - otherwise "CRI>95 optional" gets
   scheduled as the fitting's CRI. */
function dropOptionsColumn(text) {
    const lines = String(text).split('\n');
    let col = -1, start = -1;
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const m = line.match(/\bOptions?\b/i);
        if (!m) continue;
        const at = m.index;
        const after = line.slice(at + m[0].length).trim();
        const before = line.slice(0, at);
        if (at > 20 && after.length <= 2 && before.trim().length && /\s{3,}$/.test(before)) {
            col = at; start = i; break;
        }
    }
    if (col < 0) return text;
    /* strip only until the next heading appears in that column ("Size & Weight"),
       so genuine right-column specs below the options are kept */
    const out = lines.slice();
    for (let i = start; i < lines.length; i++) {
        const right = (lines[i].length > col ? lines[i].slice(col) : '').trim();
        if (i > start && right && /^[A-Z][A-Za-z&.\s]{3,26}:?$/.test(right)) break;
        out[i] = lines[i].length > col ? lines[i].slice(0, col) : lines[i];
    }
    return out.join('\n');
}

/* Rebuild visual lines from pdf.js text items.
   Datasheets are label/value tables: a label and its value sit on the same
   line but arrive as separate items. Flattening the page into one string
   destroys that pairing, so group items by their y position first. */
function linesFromTextContent(tc) {
    /* Group items into visual lines by CLUSTERING their y positions, not by rounding
       into fixed buckets. Two items at y=650.98 and y=651.02 are on the same line, but
       rounding to a 2pt grid puts them in different buckets - which silently split
       label from value on some sheets and not others. */
    const items = [];
    tc.items.forEach(it => {
        if (!it.str || !it.str.trim()) return;
        const tr = it.transform || [];
        items.push({
            y: tr[5] || 0, x: tr[4] || 0,
            w: it.width || 0, h: it.height || Math.abs(tr[3]) || 8, s: it.str
        });
    });
    if (!items.length) return '';

    items.sort((a, b) => b.y - a.y);
    const lines = [];
    let cur = [items[0]];
    for (let k = 1; k < items.length; k++) {
        const it = items[k];
        const ref = cur[cur.length - 1];
        const tol = Math.max(2, Math.min(ref.h, it.h) * 0.6);
        if (Math.abs(ref.y - it.y) <= tol) cur.push(it);
        else { lines.push(cur); cur = [it]; }
    }
    lines.push(cur);

    return lines.map(row => {
        row.sort((a, b) => a.x - b.x);
        let line = '', prevEnd = null;
        for (const it of row) {
            if (prevEnd !== null) {
                /* Join by the measured gap: pdf.js splits "QS38.43" into "QS38" and
                   ".43", and inserting a space there corrupts order codes. */
                const gap = it.x - prevEnd;
                const charW = (it.w && it.s.length) ? it.w / it.s.length : 5;
                if (gap > charW * 3) line += '   ';
                else if (gap > charW * 0.28) line += ' ';
            }
            line += it.s;
            prevEnd = it.x + (it.w || 0);
        }
        return line.replace(/\s{2,}/g, '   ').trim();
    }).join('\n');
}

/* Extract LFS cell values from a PDF datasheet (fills only blank cells) */

/* ============================================================================
   LLM GAP FILLER

   The rule-based scanner above is the source of truth: it is deterministic,
   auditable and regression-tested. This only runs afterwards, and only on the
   cells it left BLANK. It never overwrites a value the parser found and never
   touches a value you typed.

   Anything it fills is marked as a suggestion (dashed amber) so you can see at
   a glance which numbers came from a model rather than from a rule.

   The API key must never appear in this file - it is browser JavaScript and
   anyone can read it. The request goes to llm-extract.php on our own server,
   which holds the key. If that file is missing or has no key configured, the
   call fails quietly and the tool behaves exactly as it did before.
   ========================================================================== */
const LLM = {
    endpoint: 'llm-extract.php',
    available: null,          // null = untried, false = off, true = working

    /* What we are willing to ask a model for, and how we describe each one.
       Kept deliberately narrow: no CONTROL (a design decision, not a fact)
       and no TAG or LOCATION (yours to choose). */
    FIELDS: {
        description: 'The type of fitting in two or three words, e.g. DOWNLIGHT, STRIP LIGHT, BOLLARD, WALL LIGHT. Not the mounting method.',
        finish:      'The visible finish or body colour, e.g. WHITE, TEXTURED BLACK, ANODISED SILVER.',
        dimensions:  'Overall size of the fitting itself, never the packaging or the cut-out. Format round fittings as "89mm(DIA) x 74mm(H)" and rectangular as "600mm(L) x 100mm(W) x 75mm(H)".',
        ip:          'Ingress protection rating exactly as printed, e.g. IP20, IP65.',
        source:      'Colour temperature, circuit watts and delivered lumens, one per line, e.g. "3000K\\n13.5W\\n1650lm".',
        cri:         'Colour rendering index, e.g. 90, >90, 80+.',
        sdcm:        'MacAdam ellipse / colour consistency, e.g. 3 or <3.',
        lifetime:    'Rated life with its L and B figures if given, e.g. "L80B10\\n>60,000h".',
        mounting:    'How it installs: RECESSED, SURFACE MOUNTED, SUSPENDED, TRACK, IN GROUND, SURFACE WALL.',
        driver:      'Supply or dimming protocol only: DALI, 240V, 24V, 12V, 0-10V, PHASE DIMMABLE.',
        model:       'Product name only - the marketing name a person would say out loud, e.g. "Laser Blade XS", NOT the order code.'
    },

    async fill(row, missing, text) {
        if (this.available === false) return [];
        /* only ask about cells that are genuinely empty right now */
        const want = missing.filter(k => this.FIELDS[k] && !cellText(row, k));
        if (!want.length || !text) return [];

        let data;
        try {
            const res = await fetch(this.endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    fields: want.reduce((o, k) => (o[k] = this.FIELDS[k], o), {}),
                    text: text.slice(0, 24000)
                })
            });
            if (!res.ok) { this.available = false; return []; }
            data = await res.json();
        } catch { this.available = false; return []; }

        if (!data || typeof data !== 'object' || data.error) { this.available = false; return []; }
        this.available = true;

        const got = [];
        row.suggested = row.suggested || [];
        for (const k of want) {
            let v = data[k];
            if (typeof v !== 'string') continue;
            v = v.trim();
            /* the model is told to answer UNKNOWN rather than guess - honour it */
            if (!v || /^(unknown|n\/a|none|null|-)$/i.test(v)) continue;
            if (cellText(row, k)) continue;             // never overwrite
            row.cells[k] = k === 'model'
                ? modelCell(v, detectSupplier(text), '')
                : scheduleCase(v);
            if (!row.suggested.includes(k)) row.suggested.push(k);
            got.push(k);
        }
        return got;
    }
};

async function pdfIntoRow(row, file, onProgress) {
    pdfjsLib.GlobalWorkerOptions.workerSrc =
        'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    onProgress(8);
    const buf = await file.arrayBuffer();
    onProgress(18);
    const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
    onProgress(30);
    let text = '';
    const nPages = Math.min(pdf.numPages, 6);
    for (let p = 1; p <= nPages; p++) {
        const page = await pdf.getPage(p);
        const tc = await page.getTextContent();
        text += linesFromTextContent(tc) + '\n';
        onProgress(30 + Math.round(60 * p / nPages));
    }

    /* keep the text so the app can learn from any corrections you make later */
    FileStore.putText(row.id, text.slice(0, 200000)).catch(() => { });

    const filled = [];
    const fill = (key, val) => {
        /* one place where every scanned value is normalised to schedule case:
           CAPS, but mm / lm / h / lm/W stay lowercase */
        if (val && !(row.cells[key] || '').trim()) { row.cells[key] = scheduleCase(val); filled.push(key); }
    };

    fill('ip', extractIp(text));

    fill('source', [extractCct(text), extractWatts(text), extractLumens(text)]
        .filter(Boolean).join('\n') || null);

    fill('cri', extractCri(text));
    fill('sdcm', detectSdcm(text));
    fill('lifetime', detectLifetime(text));
    fill('beam', extractBeam(text));
    fill('finish', extractFinish(text));
    fill('driver', extractDriver(text));
    /* CONTROL is a design decision, not a datasheet fact - never auto-filled */

    fill('dimensions', detectDimensions(text));

    const category = labelValue(text, 'category', 34);
    const title = titleLineParts(text);
    const productName = (labelValue(text, 'name', 60).split(/\s{2,}/)[0].trim())
        || (title ? title.name : '');
    /* the opening block of a datasheet names the fitting type far more reliably
       than body copy, so treat it as part of the name */
    const headline = text.split('\n').filter(l => l.trim()).slice(0, 8).join(' ');
    fill('mounting', categoryToMounting(category) || detectMounting(text));
    fill('description', describeFitting(productName || headline, category, text, file.name));

    /* the headline paragraph names the fitting type far more reliably than
       body copy: "OPERATING THEATRE CRI95+ Plaster/Sandwich panel Single Luminaire..." */
    const stem = stripLanguageSuffix(file.name.replace(/\.pdf$/i, ''))
        .replace(/\b(data\s*sheet|product\s*specifications?)\b/ig, '')
        .trim();
    const codeInName = stem.match(/[([]([\w.\-]{6,})[)\]]/);
    const labelName = labelValue(text, 'name', 60).split(/\s{2,}/)[0].trim();
    const labelCode = labelValue(text, 'code', 30).split(/\s+/)[0].trim();
    /* the title line ('Blade R / QS38.43 Black') names the product far better than
       the filename, which is often just the order code */
    const supplier = detectSupplier(text + ' ' + file.name);
    const modelNameRaw = cleanProductName(labelName || (title && title.name) || '');
    /* only use it if it reads like a product name, not an order code; if the
       sheet gave us nothing usable, try the filename, and if that fails too
       leave the name out and keep just the manufacturer and code */
    const modelName = looksLikeProductName(modelNameRaw)
        ? modelNameRaw
        : nameFromFilename(stem, supplier);
    const code = (/^[\w.\-\/]{4,}$/.test(labelCode) && labelCode) ||
        (title && title.code) ||
        (codeInName ? codeInName[1] : '') ||
        (/^[A-Z]\d{6,}[A-Z]{0,3}$/i.test(stem) ? stem : '');
        fill('model', modelCell(modelName, supplier, code) || null);

    /* ---- anything still blank: try headings learned from your past corrections ---- */
    const LEARNABLE = {
        ip: x => /IP\s?\d{2}/i.test(x),
        cri: x => /\d{2}/.test(x),
        sdcm: x => /\d/.test(x),
        lifetime: x => /\d{3,}|L\d{2,3}/i.test(x),
        beam: x => /\d{1,3}\s*°/.test(x),
        finish: x => /[a-z]{3}/i.test(x),
        dimensions: x => /\d+\s*mm/i.test(x),
        mounting: x => /[a-z]{3}/i.test(x),
        driver: x => /[a-z0-9]{2}/i.test(x),
        description: x => /[a-z]{3}/i.test(x)
    };
    for (const [key, ok] of Object.entries(LEARNABLE)) {
        if ((row.cells[key] || '').trim()) continue;
        const v = learnedValue(text, key, ok);
        if (v) { row.cells[key] = scheduleCase(v); filled.push(key); }
    }

    /* ---- apply corrections you have made before for this manufacturer ---- */
    for (const c of COLS) {
        const fix = Learning.correctionFor(supplier, c.key, row.cells[c.key]);
        if (fix) row.cells[c.key] = fix;
    }

    /* remember what the scan produced, so an edit can be recognised as a correction */
    row.scan = { supplier, cells: { ...row.cells } };

    onProgress(100);
    return filled;
}

/* ==================== STATE ==================== */

const LS_KEY = 'plexus-lfs-v4';

function newProject(name) {
    return {
        id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
        name: name || 'Untitled project',
        title: 'LIGHT FITTING SCHEDULE',
        rows: [], colWidths: {}, hiddenCols: {}, scans: []
    };
}

function cleanProject(p) {
    return {
        id: p.id, name: p.name, title: p.title,
        colWidths: p.colWidths || {}, hiddenCols: p.hiddenCols || {}, scans: p.scans || [],
        rows: (p.rows || []).map(r => ({ ...r, loading: null }))
    };
}

const Store = {
    /* Workspace shape: { projects: [...], currentId, savedAt } */
    load() {
        try {
            const s = JSON.parse(localStorage.getItem(LS_KEY));
            if (s && s.projects && s.projects.length) {
                s.projects.forEach(p => (p.rows || []).forEach(r => {
                    r.loading = null;
                    /* Schedules saved by an earlier build stored units in capitals
                       ("1650LM", "60,000H"). Re-normalise on load so old work and
                       new scans read the same. */
                    Object.keys(r.cells || {}).forEach(k => {
                        const v = r.cells[k];
                        if (typeof v === 'string' && /\d\s?(MM|LM|HRS?)\b/.test(v)) {
                            r.cells[k] = scheduleCase(v);
                        }
                    });
                }));
                if (!s.projects.some(p => p.id === s.currentId)) s.currentId = s.projects[0].id;
                return s;
            }
            /* migrate the earlier single-schedule format */
            if (s && s.rows) {
                s.rows.forEach(r => { r.loading = null; });
                const p = { ...newProject('My schedule'), ...s };
                if (!p.id) p.id = newProject().id;
                return { projects: [p], currentId: p.id, savedAt: s.savedAt };
            }
        } catch { /* ignore */ }
        const p = newProject('My schedule');
        return { projects: [p], currentId: p.id };
    },
    save(db) {
        if (!db || !db.projects) return;
        localStorage.setItem(LS_KEY, JSON.stringify({
            projects: db.projects.map(cleanProject),
            currentId: db.currentId,
            savedAt: db.savedAt
        }));
    }
};

/* Datasheet files live in IndexedDB so they survive reloads and stay openable */
const FileStore = {
    _db: null,
    open() {
        return new Promise((res, rej) => {
            if (this._db) return res(this._db);
            const rq = indexedDB.open('plexus-lfs-files', 3);
            rq.onupgradeneeded = () => {
                const db = rq.result;
                if (!db.objectStoreNames.contains('files')) db.createObjectStore('files');
                if (!db.objectStoreNames.contains('meta')) db.createObjectStore('meta');
                /* extracted text, kept so the app can learn from your corrections */
                if (!db.objectStoreNames.contains('texts')) db.createObjectStore('texts');
            };
            rq.onsuccess = () => { this._db = rq.result; res(this._db); };
            rq.onerror = () => rej(rq.error);
        });
    },
    async putMeta(key, val) {
        const db = await this.open();
        return new Promise((res, rej) => {
            const tx = db.transaction('meta', 'readwrite');
            tx.objectStore('meta').put(val, key);
            tx.oncomplete = res;
            tx.onerror = () => rej(tx.error);
        });
    },
    async getMeta(key) {
        const db = await this.open();
        return new Promise((res, rej) => {
            const rq = db.transaction('meta').objectStore('meta').get(key);
            rq.onsuccess = () => res(rq.result);
            rq.onerror = () => rej(rq.error);
        });
    },
    async putText(id, txt) {
        const db = await this.open();
        return new Promise((res, rej) => {
            const tx = db.transaction('texts', 'readwrite');
            tx.objectStore('texts').put(txt, id);
            tx.oncomplete = res;
            tx.onerror = () => rej(tx.error);
        });
    },
    async getText(id) {
        const db = await this.open();
        return new Promise((res, rej) => {
            const rq = db.transaction('texts').objectStore('texts').get(id);
            rq.onsuccess = () => res(rq.result);
            rq.onerror = () => rej(rq.error);
        });
    },
    async put(id, blob) {
        const db = await this.open();
        return new Promise((res, rej) => {
            const tx = db.transaction('files', 'readwrite');
            tx.objectStore('files').put(blob, id);
            tx.oncomplete = res;
            tx.onerror = () => rej(tx.error);
        });
    },
    async get(id) {
        const db = await this.open();
        return new Promise((res, rej) => {
            const rq = db.transaction('files').objectStore('files').get(id);
            rq.onsuccess = () => res(rq.result);
            rq.onerror = () => rej(rq.error);
        });
    },
    async del(id) {
        const db = await this.open();
        return new Promise((res) => {
            const tx = db.transaction('files', 'readwrite');
            tx.objectStore('files').delete(id);
            tx.oncomplete = res;
            tx.onerror = res;
        });
    }
};

async function openScanFile(scan) {
    try {
        const blob = await FileStore.get(scan.id);
        if (!blob) { toast('File not stored for this scan'); return; }
        const type = /\.pdf$/i.test(scan.name) ? 'application/pdf' : 'text/plain';
        const url = URL.createObjectURL(new Blob([blob], { type }));
        window.open(url, '_blank');
    } catch {
        toast('Could not open the stored file');
    }
}

/* ==================== LEARNING FROM YOUR CORRECTIONS ====================
   Two things are learned, both from evidence rather than guesswork:

   1. CORRECTIONS - you change a scanned value, so the same scan result from the
      same manufacturer is corrected automatically next time.
   2. LABELS - you fill a cell the scan missed, and your value appears verbatim in
      the datasheet next to a heading we did not know. That heading is added to the
      vocabulary for that field.

   Learned rules only ever fill blanks or replace an identical scan result. They
   never overwrite something you typed, and everything is inspectable and erasable. */

const LS_LEARN = 'plexus-lfs-learning';

const Learning = {
    data: { corrections: {}, labels: {} },

    load() {
        try {
            const d = JSON.parse(localStorage.getItem(LS_LEARN));
            if (d && d.corrections && d.labels) this.data = d;
        } catch { /* start fresh */ }
        return this.data;
    },
    save() { try { localStorage.setItem(LS_LEARN, JSON.stringify(this.data)); } catch { /* full */ } },

    count() {
        return Object.keys(this.data.corrections).length +
            Object.values(this.data.labels).reduce((n, a) => n + a.length, 0);
    },
    clear() { this.data = { corrections: {}, labels: {} }; this.save(); },

    _ck(supplier, field, from) {
        return (supplier || 'ANY').toUpperCase() + '|' + field + '|' + stripMd(from).trim().toUpperCase();
    },

    /* record: the scan said `from`, you changed it to `to` */
    addCorrection(supplier, field, from, to) {
        if (!from || !to || stripMd(from).trim().toUpperCase() === stripMd(to).trim().toUpperCase()) return false;
        this.data.corrections[this._ck(supplier, field, from)] = to;
        this.save();
        return true;
    },

    correctionFor(supplier, field, value) {
        if (!value) return null;
        return this.data.corrections[this._ck(supplier, field, value)] ||
            this.data.corrections[this._ck('ANY', field, value)] || null;
    },

    /* record: this heading holds this field's value on this manufacturer's sheets */
    addLabel(field, label, supplier) {
        const lab = label.trim().toLowerCase();
        if (!lab || lab.length < 3 || lab.length > 44) return false;
        if ((SPEC_LABELS[field] || []).some(l => l.toLowerCase() === lab)) return false;
        const list = this.data.labels[field] || (this.data.labels[field] = []);
        const hit = list.find(x => x.label === lab);
        if (hit) { hit.count++; hit.supplier = hit.supplier || supplier; }
        else list.push({ label: lab, supplier: supplier || '', count: 1 });
        this.save();
        return !hit;
    },

    labelsFor(field) { return (this.data.labels[field] || []).map(x => x.label); }
};

/* Try any learned headings for a field that the built-in vocabulary missed */
function learnedValue(text, field, validate) {
    for (const label of Learning.labelsFor(field)) {
        const v = labelValue(text, field, 64, label, validate);
        if (v) return v;
    }
    return '';
}

/* Called when you edit a cell on a scanned row */
async function learnFromEdit(row, field, newValue) {
    if (!row || !row.scanned || !row.scan) return;
    const supplier = row.scan.supplier || '';
    const before = (row.scan.cells && row.scan.cells[field]) || '';
    const after = stripMd(newValue).trim();
    if (!after) return;

    /* 1. a straight correction of something the scan produced */
    if (before && stripMd(before).trim().toUpperCase() !== after.toUpperCase()) {
        if (Learning.addCorrection(supplier, field, before, newValue)) {
            toast(`Learned: ${supplier || 'this manufacturer'} ${FIELD_LABELS[field] || field} "${stripMd(before).split('\n')[0]}" -> "${after.split('\n')[0]}"`, 3800);
        }
        return;
    }

    /* 2. the scan found nothing - can we see your value in the datasheet? */
    if (before) return;
    let text = '';
    try { text = await FileStore.getText(row.id) || ''; } catch { /* no stored text */ }
    if (!text) return;

    const needle = after.split('\n')[0].trim();
    if (needle.length < 2) return;
    const lines = text.split('\n');
    for (const line of lines) {
        const at = line.toUpperCase().indexOf(needle.toUpperCase());
        if (at <= 0) continue;
        /* the heading is whatever sits to the left of your value on that line */
        const head = line.slice(0, at).trim().replace(/[:\-–]\s*$/, '').trim();
        if (!head || head.length > 44 || !/[a-z]/i.test(head)) continue;
        if (/\d{3,}/.test(head)) continue;                 // a value, not a heading
        if (Learning.addLabel(field, head, supplier)) {
            toast(`Learned: "${head}" means ${FIELD_LABELS[field] || field} on ${supplier || 'these'} datasheets`, 4200);
            renderLearningNote();
        }
        return;
    }
}

/* ==================== AUTO-SAVE TO A PROJECT FILE ====================
   Browser storage is the live cache; linking a project file (ideally in a
   OneDrive/synced folder) writes everything - schedule, settings and stored
   datasheets - to disk automatically after every change. */

function bufToB64(buf) {
    const bytes = new Uint8Array(buf);
    let s = '';
    for (let i = 0; i < bytes.length; i += 0x8000) {
        s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(s);
}

function b64ToBlob(b64, type) {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type });
}

/* The project file holds the WHOLE workspace: every project plus its datasheets */
async function serializeProject() {
    db.savedAt = Date.now();
    syncScans();
    const files = [];
    for (const p of db.projects) {
        for (const s of (p.scans || [])) {
            try {
                const blob = await FileStore.get(s.id);
                if (blob) files.push({ id: s.id, name: s.name, b64: bufToB64(await blob.arrayBuffer()) });
            } catch { /* skip unstorable file */ }
        }
    }
    return {
        app: 'plexus-lfs', version: 2, savedAt: db.savedAt,
        projects: db.projects.map(cleanProject), currentId: db.currentId, files
    };
}

async function adoptProject(obj) {
    if (obj.projects && obj.projects.length) {
        db.projects = obj.projects.map(p => ({ ...newProject(p.name), ...p }));
        db.currentId = obj.projects.some(p => p.id === obj.currentId) ? obj.currentId : db.projects[0].id;
    } else {
        /* a v1 file holds a single schedule */
        const p = { ...newProject('Imported schedule'), ...obj };
        p.rows = (obj.rows || []).map(r => ({ ...blankRow(), ...r, loading: null }));
        db.projects = [p];
        db.currentId = p.id;
    }
    db.savedAt = obj.savedAt || Date.now();
    for (const f of (obj.files || [])) {
        const type = /\.pdf$/i.test(f.name) ? 'application/pdf' : 'text/plain';
        try { await FileStore.put(f.id, b64ToBlob(f.b64, type)); } catch { /* ignore */ }
    }
    Store.save(db);
    useProject(db.currentId);
}

const ProjectFile = {
    handle: null,
    status: 'none', // none | prompt | granted
    _t: null,

    async init() {
        try { this.handle = await FileStore.getMeta('projectHandle'); } catch { /* ignore */ }
        if (!this.handle) { this.refreshButton(); return; }
        try {
            const p = await this.handle.queryPermission({ mode: 'readwrite' });
            this.status = p === 'granted' ? 'granted' : 'prompt';
        } catch { this.status = 'prompt'; }
        if (this.status === 'granted') await this.syncFromFile();
        this.refreshButton();
    },

    async link() {
        if (!window.showSaveFilePicker) {
            toast('File auto-save needs Chrome or Edge');
            return;
        }
        let handle;
        try {
            handle = await showSaveFilePicker({
                suggestedName: ((state.name || stripMd(state.title) || 'light-fitting-schedule')
                    .toLowerCase().replace(/[^\w-]+/g, '-').replace(/^-+|-+$/g, '') || 'lfs') + '.lfs.json',
                types: [{ description: 'LFS project file', accept: { 'application/json': ['.json'] } }]
            });
        } catch { return; } // cancelled
        this.handle = handle;
        try { await FileStore.putMeta('projectHandle', handle); } catch { /* ignore */ }
        this.status = 'granted';
        await this.write();
        this.refreshButton();
        toast('Auto-saving to ' + handle.name + ' - keep it in a synced folder for backup');
    },

    async reconnect() {
        try {
            if (await this.handle.requestPermission({ mode: 'readwrite' }) !== 'granted') return;
            this.status = 'granted';
            await this.syncFromFile();
            this.refreshButton();
            toast('Auto-save reconnected (' + this.handle.name + ')');
        } catch { /* ignore */ }
    },

    async syncFromFile() {
        try {
            const f = await this.handle.getFile();
            if (f.size) {
                const obj = JSON.parse(await f.text());
                if (obj.app === 'plexus-lfs' && (obj.savedAt || 0) > (db.savedAt || 0)) {
                    await adoptProject(obj); // the file is newer (edited on another machine)
                    return;
                }
            }
        } catch { /* unreadable - fall through and overwrite */ }
        await this.write();
    },

    schedule() {
        if (this.status !== 'granted') return;
        clearTimeout(this._t);
        this._t = setTimeout(() => this.write(), 1500);
    },

    async write() {
        if (!this.handle || this.status !== 'granted') return;
        try {
            const data = await serializeProject();
            const w = await this.handle.createWritable();
            await w.write(JSON.stringify(data));
            await w.close();
        } catch { /* keep the localStorage copy; retry on next change */ }
    },

    refreshButton() {
        const lbl = $('save-file-label');
        const btn = $('save-file');
        if (!lbl || !btn) return;
        if (this.status === 'granted') {
            lbl.textContent = 'Auto-saving ✓';
            btn.title = 'Saved to ' + this.handle.name + ' - click to save now';
        } else if (this.status === 'prompt') {
            lbl.textContent = 'Reconnect save file';
            btn.title = 'Click to reconnect ' + (this.handle && this.handle.name ? this.handle.name : 'your save file');
        } else {
            lbl.textContent = 'Save to file…';
        }
    }
};

let db = null;      // { projects: [...], currentId }
let state = null;   // the CURRENT project - all existing code reads state.rows/title/...
let globalSearch = '';
const scans = [];        // {id, name, pct, status:'busy'|'done'|'error', note}

const $ = (id) => document.getElementById(id);

let _saveT = null;
function persist() {
    clearTimeout(_saveT);
    _saveT = setTimeout(() => Store.save(db), 300);
    ProjectFile.schedule();
}

/* ==================== PROJECTS ==================== */

function renderProjectSelect() {
    const sel = $('project-select');
    sel.innerHTML = '';
    db.projects.forEach(p => {
        const o = document.createElement('option');
        o.value = p.id;
        o.textContent = p.name;
        sel.appendChild(o);
    });
    sel.value = db.currentId;
    sel.title = db.projects.length > 1 ? 'Switch project (' + db.projects.length + ')' : 'Project';
}

/* Point `state` at a project and redraw everything that belongs to it */
function useProject(id) {
    const p = db.projects.find(x => x.id === id) || db.projects[0];
    db.currentId = p.id;
    state = p;
    state.rows = state.rows || [];
    state.colWidths = state.colWidths || {};
    state.hiddenCols = state.hiddenCols || {};
    state.scans = state.scans || [];
    /* datasheets are per project */
    scans.length = 0;
    scans.push(...state.scans);
    globalSearch = '';
    scanSearch = '';
    const gs = $('global-search'), ss = $('scan-search');
    if (gs) gs.value = '';
    if (ss) ss.value = '';
    renderProjectSelect();
    renderHead();
    renderBody();
    autosizeAll();
    renderFilterBadge();
    renderScanList();
    $('schedule-title').value = state.title || '';
    persist();
}

function toast(msg, ms = 2800) {
    const t = $('toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(t._h);
    t._h = setTimeout(() => t.classList.remove('show'), ms);
}

/* ==================== TABS ==================== */

function showTab(which) {
    $('panel-datasheets').classList.toggle('hidden', which !== 'datasheets');
    $('panel-schedule').classList.toggle('hidden', which !== 'schedule');
    $('tab-btn-datasheets').classList.toggle('active', which === 'datasheets');
    $('tab-btn-schedule').classList.toggle('active', which === 'schedule');
}

/* ==================== RENDER: TABLE ==================== */

function cellText(row, key) { return stripMd(row.cells[key] || '').trim(); }

/* Every search term must appear somewhere in the row (terms can hit different cells,
   so "3000K IP54" matches a row with 3000K in one cell and IP54 in another) */
function rowMatchesTerms(row, terms) {
    return terms.every(t => COLS.some(c => cellText(row, c.key).toLowerCase().includes(t)));
}

function searchTerms(q) { return q.toLowerCase().split(/\s+/).filter(Boolean); }

function rowVisible(row) {
    if (globalSearch) {
        if (!rowMatchesTerms(row, searchTerms(globalSearch))) return false;
    }
    return true;
}

/* ---------- column visibility (eye toggles) ---------- */

function colHidden(key) { return !!(state.hiddenCols && state.hiddenCols[key]); }

function toggleCol(key) {
    if (!state.hiddenCols) state.hiddenCols = {};
    if (state.hiddenCols[key]) delete state.hiddenCols[key];
    else state.hiddenCols[key] = true;
    persist();
    renderHead();
    renderBody();
    autosizeAll();
    renderFilterBadge();
    if (!$('filter-panel').classList.contains('hidden')) renderFilterPanel();
}

const DOC_SVG = '<svg class="ic" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 15h6M9 11h2"/></svg>';
const DOC_ADD_SVG = '<svg class="ic" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M12 18v-6M9 15h6"/></svg>';
const EYE_SVG = '<svg class="ic" viewBox="0 0 24 24"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>';
const EYE_OFF_SVG = '<svg class="ic" viewBox="0 0 24 24"><path d="M17.9 17.9A10.4 10.4 0 0 1 12 19C5 19 1 12 1 12a19.6 19.6 0 0 1 5.1-5.9M9.9 4.2A9.5 9.5 0 0 1 12 5c7 0 11 7 11 7a19.6 19.6 0 0 1-3.2 4.2"/><path d="M1 1l22 22"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
const BIN_SVG = '<svg class="ic" viewBox="0 0 24 24"><path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>';

function renderHead() {
    const tr = document.createElement('tr');
    const thE = document.createElement('th');
    thE.className = 'c-eye';
    thE.title = 'Include in export';
    thE.innerHTML = EYE_SVG;
    tr.appendChild(thE);


    COLS.forEach(c => {
        const th = document.createElement('th');
        th.style.width = colWidth(c.key) + 'px';
        th.dataset.key = c.key;
        if (colHidden(c.key)) th.classList.add('col-hidden');

        const lbl = document.createElement('span');
        lbl.textContent = c.label;
        th.appendChild(lbl);

        const rz = document.createElement('div');
        rz.className = 'col-resizer';
        rz.title = 'Drag to resize · double-click to autosize';
        rz.addEventListener('mousedown', (e) => startColResize(e, c.key, th, rz));
        rz.addEventListener('dblclick', (e) => { e.stopPropagation(); autosizeColumn(c.key, th); });
        th.appendChild(rz);

        tr.appendChild(th);
    });
    const thD = document.createElement('th');
    thD.className = 'c-doc';
    thD.title = 'Datasheet';
    thD.innerHTML = DOC_SVG;
    tr.appendChild(thD);

    const thA = document.createElement('th');
    thA.className = 'c-actions';
    thA.title = 'Delete row';
    thA.innerHTML = BIN_SVG;
    tr.appendChild(thA);
    $('lfs-head').innerHTML = '';
    $('lfs-head').appendChild(tr);
}

/* ---------- column widths: drag resize + double-click autosize ---------- */

function colWidth(key) {
    return (state.colWidths && state.colWidths[key]) || COLS.find(c => c.key === key).px;
}

function setColWidth(key, px) {
    if (!state.colWidths) state.colWidths = {};
    state.colWidths[key] = Math.round(Math.max(42, Math.min(820, px)));
    persist();
}

function startColResize(e, key, th, rz) {
    e.preventDefault();
    const startX = e.clientX;
    const startW = th.getBoundingClientRect().width;
    document.body.classList.add('col-resizing');
    rz.classList.add('dragging');

    const move = (ev) => {
        const w = Math.max(42, Math.min(820, startW + (ev.clientX - startX)));
        th.style.width = w + 'px';
    };
    const up = (ev) => {
        document.removeEventListener('mousemove', move);
        document.removeEventListener('mouseup', up);
        document.body.classList.remove('col-resizing');
        rz.classList.remove('dragging');
        setColWidth(key, startW + (ev.clientX - startX));
    };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
}

let _measureCtx = null;
function measureWidth(text, font) {
    if (!_measureCtx) _measureCtx = document.createElement('canvas').getContext('2d');
    _measureCtx.font = font;
    return _measureCtx.measureText(text).width;
}

function naturalWidth(key) {
    const cellFont = '13.5px "Arial Narrow", Arial, sans-serif';
    const headFont = 'bold 14.5px "Arial Narrow", Arial, sans-serif';
    const label = COLS.find(c => c.key === key).label;
    let w = measureWidth(label, headFont) + 26;
    state.rows.forEach(r => {
        if (r.loading) return;
        stripMd(r.cells[key] || '').split('\n').forEach(line => {
            w = Math.max(w, measureWidth(line, cellFont) + 22);
        });
    });
    return Math.round(Math.max(42, Math.min(520, w)));
}

function autosizeColumn(key, th) {
    setColWidth(key, naturalWidth(key));
    th.style.width = colWidth(key) + 'px';
}

/* Autosize every column that the user hasn't manually resized.
   Widths act as proportions (the table always fits the window),
   so this runs on open and after scans to keep everything visible. */
function autosizeAll() {
    const ths = $('lfs-head').querySelectorAll('th[data-key]');
    ths.forEach(th => {
        const key = th.dataset.key;
        th.style.width = ((state.colWidths && state.colWidths[key]) || naturalWidth(key)) + 'px';
    });
}

function renderBody() {
    const tbody = $('lfs-body');
    tbody.innerHTML = '';
    let shown = 0;

    state.rows.forEach((row) => {
        /* scanning row: spinner + progress bar instead of cells */
        if (row.loading) {
            const tr = document.createElement('tr');
            tr.className = 'scanning-row';
            tr.dataset.id = row.id;
            const td = document.createElement('td');
            td.colSpan = COLS.length + 3;
            td.innerHTML = `
                <div class="scanning-cell">
                    <div class="spinner"></div>
                    <span>Scanning <strong>${esc(row.loading.name)}</strong>…</span>
                    <div class="scan-bar"><div style="width:${row.loading.pct}%"></div></div>
                    <span class="scan-pct">${row.loading.pct}%</span>
                </div>`;
            tbody.appendChild(tr);
            shown++;
            return;
        }

        if (!rowVisible(row)) return;
        shown++;
        const tr = document.createElement('tr');
        tr.dataset.id = row.id;
        if (row.hidden) tr.classList.add('row-excluded');

        /* eye: include/exclude this row from the export */
        const tdE = document.createElement('td');
        tdE.className = 'c-eye';
        const eye = document.createElement('button');
        eye.className = 'row-eye';
        eye.innerHTML = row.hidden ? EYE_OFF_SVG : EYE_SVG;
        eye.title = row.hidden ? 'Hidden from export - click to include' : 'Included in export - click to hide';
        eye.addEventListener('click', () => {
            row.hidden = !row.hidden;
            persist();
            renderBody();
        });
        tdE.appendChild(eye);
        tr.appendChild(tdE);

        COLS.forEach(c => {
            const td = document.createElement('td');
            if (c.key === 'tag') td.className = 'cell-tag';
            if (colHidden(c.key)) td.classList.add('col-hidden');
            if (row.scanned && !cellText(row, c.key) && SCAN_TARGET_KEYS.includes(c.key)) {
                td.classList.add('needs-fill');
            }
            /* filled by the model rather than by a rule - worth your eye */
            if ((row.suggested || []).includes(c.key) && cellText(row, c.key)) {
                td.classList.add('suggested');
                td.title = 'Suggested by AI from the datasheet - please check';
            }
            const div = document.createElement('div');
            div.className = 'cell';
            div.contentEditable = 'true'; // rich editing so Ctrl+B bold works
            div.innerHTML = mdToHtml(row.cells[c.key] || '');
            div.addEventListener('input', () => {
                row.cells[c.key] = scheduleCase(htmlToMd(div, false).replace(/\n{3,}/g, '\n\n'));
                if (td.classList.contains('needs-fill') && cellText(row, c.key)) td.classList.remove('needs-fill');

                /* keep the '-' placeholder working: a fully cleared cell must be truly empty */
                if (!cellText(row, c.key)) {
                    row.cells[c.key] = '';
                    if (div.innerHTML !== '') div.innerHTML = '';
                }

                /* tag prefix drives the description (only touches blank or auto-set values,
                   and clears it again when the tag no longer matches) */
                if (c.key === 'tag') {
                    const auto = descFromTag(row.cells.tag); // '' when the tag matches nothing
                    const cur = cellText(row, 'description');
                    if ((cur === '' || AUTO_DESCS.has(cur)) && auto !== cur) {
                        row.cells.description = auto;
                        const descIdx = COLS.findIndex(x => x.key === 'description') + 1; // +1 for the eye column
                        const descTd = tr.children[descIdx];
                        if (descTd) {
                            const descDiv = descTd.querySelector('.cell');
                            if (descDiv) descDiv.innerHTML = mdToHtml(auto);
                            descTd.classList.toggle('needs-fill', !auto && !!row.scanned);
                        }
                    }
                }
                persist();
            });
            div.addEventListener('focus', () => { div._before = row.cells[c.key] || ''; });
            div.addEventListener('blur', () => {
                /* CSS no longer fakes uppercase, so redraw from the normalised
                   value once editing stops: you type freely, it settles to
                   schedule case (CAPS with lowercase mm / lm / h). */
                const settled = mdToHtml(row.cells[c.key] || '');
                if (div.innerHTML !== settled) div.innerHTML = settled;
                if (row.scanned && !cellText(row, c.key) && SCAN_TARGET_KEYS.includes(c.key)) {
                    td.classList.add('needs-fill');
                }
                /* you finished editing a scanned row - see if there is a rule to learn */
                if (row.scanned && (row.cells[c.key] || '') !== (div._before || '')) {
                    learnFromEdit(row, c.key, row.cells[c.key] || '');
                    /* you have confirmed or corrected it - it is no longer a guess */
                    if (row.suggested) {
                        row.suggested = row.suggested.filter(k => k !== c.key);
                        td.classList.remove('suggested');
                        td.removeAttribute('title');
                    }
                }
            });
            div.addEventListener('paste', (e) => {
                e.preventDefault(); // always paste as plain text
                document.execCommand('insertText', false, e.clipboardData.getData('text/plain'));
            });
            div.addEventListener('keydown', (e) => {
                // allow only bold formatting; block italic/underline shortcuts
                if ((e.ctrlKey || e.metaKey) && (e.key === 'i' || e.key === 'u')) e.preventDefault();
                // Enter leaves the cell; Shift+Enter makes a new line
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    div.blur();
                }
            });
            /* clicking anywhere in the cell focuses the editor */
            td.addEventListener('mousedown', (e) => {
                if (e.target === td) {
                    e.preventDefault();
                    div.focus();
                    // caret at end
                    const sel = window.getSelection();
                    sel.selectAllChildren(div);
                    sel.collapseToEnd();
                }
            });
            td.appendChild(div);
            tr.appendChild(td);
        });

        /* datasheet cell: opens this row's uploaded file, or accepts one */
        const tdD = document.createElement('td');
        tdD.className = 'c-doc';
        const linked = scans.filter(s => s.rowId === row.id);
        const docBtn = document.createElement('button');
        docBtn.className = 'row-doc';

        if (linked.length) {
            const names = linked.map(s => s.name).join('\n');
            docBtn.innerHTML = DOC_SVG;
            docBtn.title = (linked.length > 1 ? linked.length + ' files - click to open:\n' : 'Open ') + names +
                (row.ies ? `\n\nIES: beam ${row.ies.beam ?? '?'}°, field ${row.ies.field ?? '?'}°, ` +
                    `${row.ies.lumens ?? '?'} lm, ${row.ies.watts ?? '?'} W, ${row.ies.efficacy ?? '?'} lm/W` : '');
            docBtn.addEventListener('click', () => linked.forEach(openScanFile));
        } else {
            docBtn.innerHTML = DOC_ADD_SVG;
            docBtn.title = 'No datasheet - click to attach one';
            docBtn.addEventListener('click', () => {
                const inp = document.createElement('input');
                inp.type = 'file';
                inp.accept = '.pdf,.ies';
                inp.addEventListener('change', () => {
                    if (inp.files[0]) scanFileIntoRow(inp.files[0], row);
                });
                inp.click();
            });
        }
        tdD.appendChild(docBtn);
        if (linked.length > 1) {
            const n = document.createElement('span');
            n.className = 'doc-count';
            n.textContent = linked.length;
            tdD.appendChild(n);
        }
        tr.appendChild(tdD);

        const tdA = document.createElement('td');
        tdA.className = 'c-actions';
        const del = document.createElement('button');
        del.className = 'row-del';
        del.title = 'Delete row';
        del.innerHTML = BIN_SVG;
        del.addEventListener('click', () => {
            if (!confirm('Delete this row' + (row.cells.tag ? ' (' + stripMd(row.cells.tag) + ')' : '') +
                '? Its loaded datasheet will be removed too.')) return;
            removeRowAndScans(row.id);
        });
        tdA.appendChild(del);
        tr.appendChild(tdA);

        /* row as a drop target for datasheets (highlights as one block) */
        tr.addEventListener('dragover', e => {
            if (hasFiles(e)) { e.preventDefault(); e.stopPropagation(); tr.classList.add('drop-target'); }
        });
        tr.addEventListener('dragleave', e => {
            if (!tr.contains(e.relatedTarget)) tr.classList.remove('drop-target');
        });
        tr.addEventListener('drop', e => {
            if (!hasFiles(e)) return;
            e.preventDefault();
            e.stopPropagation();
            tr.classList.remove('drop-target');
            const files = [...e.dataTransfer.files].filter(f => /\.(pdf|ies)$/i.test(f.name));
            if (!files.length) { toast('Drop .pdf datasheets or .ies files'); return; }
            scanFileIntoRow(files[0], row);            // first file fills this row
            files.slice(1).forEach(f => scanFileIntoRow(f, null)); // rest become new rows
        });

        tbody.appendChild(tr);
    });

    $('add-row-cell').colSpan = COLS.length + 3;
    const total = state.rows.length;
    $('row-count').textContent = total
        ? (shown === total ? `${total} fitting${total === 1 ? '' : 's'}` : `Showing ${shown} of ${total} fittings`)
        : '';
}

function esc(s) {
    return String(s).replace(/[&<>"']/g, c =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function hasFiles(e) {
    return e.dataTransfer && [...(e.dataTransfer.types || [])].includes('Files');
}

/* ==================== RENDER: FILTTER PANEL & CHIPS ==================== */

/* One toggle per column: highlighted = included in the export, dimmed = hidden */
function renderFilterPanel() {
    const box = $('filter-columns');
    box.innerHTML = '';
    const pills = document.createElement('div');
    pills.className = 'fp-pills';
    COLS.forEach(c => {
        const on = !colHidden(c.key);
        const pill = document.createElement('button');
        pill.className = 'pill' + (on ? ' on' : '');
        pill.innerHTML = (on ? EYE_SVG : EYE_OFF_SVG) + ' ' + esc(c.label);
        pill.title = on ? 'Included in export - click to hide' : 'Hidden from export - click to include';
        pill.addEventListener('click', () => toggleCol(c.key));
        pills.appendChild(pill);
    });
    box.appendChild(pills);

    /* Show all <-> Hide all toggle label */
    const anyHidden = COLS.some(c => colHidden(c.key));
    $('filter-clear-all').textContent = anyHidden ? 'Show all' : 'Hide all';
}

function renderFilterBadge() {
    const n = Object.keys(state.hiddenCols || {}).length;
    $('filter-count').textContent = n + ' hidden';
    $('filter-count').classList.toggle('hidden', !n);
    $('filter-btn').classList.toggle('active-filters', !!n);
}

/* ==================== RENDER: SCAN LIST (Datasheets tab) ==================== */

let scanSearch = '';

function renderScanList() {
    const wrap = $('scan-list-wrap');
    const list = $('scan-list');
    wrap.classList.toggle('hidden', !scans.length);
    list.innerHTML = '';
    const terms = searchTerms(scanSearch);
    scans
        .filter(s => {
            if (!terms.length) return true;
            const own = (s.name + ' ' + (s.note || '')).toLowerCase();
            const row = s.rowId && state.rows.find(r => r.id === s.rowId);
            // each term must appear in the file name/result or anywhere in the linked row
            return terms.every(t => own.includes(t) ||
                (row && COLS.some(c => cellText(row, c.key).toLowerCase().includes(t))));
        })
        .slice(0, 50)
        .forEach(s => {
        const item = document.createElement('div');
        item.className = 'scan-item ' + s.status;
        const icon = s.status === 'busy'
            ? '<div class="spinner"></div>'
            : s.status === 'done'
                ? '<svg class="ic file" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>'
                : '<svg class="ic file" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>';
        item.innerHTML = icon +
            `<button class="scan-name" title="Open datasheet in a new tab">${esc(s.name)}</button>` +
            (s.status === 'busy'
                ? `<div class="scan-bar"><div style="width:${s.pct}%"></div></div><span class="scan-status">${s.pct}%</span>`
                : `<span class="scan-status">${esc(s.note)}</span>`);

        item.querySelector('.scan-name').addEventListener('click', () => openScanFile(s));

        if (s.status !== 'busy') {
            const x = document.createElement('button');
            x.className = 'scan-x';
            x.title = 'Remove from list';
            x.innerHTML = '<svg class="ic" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>';
            x.addEventListener('click', () => {
                const hasRow = s.rowId && state.rows.some(r => r.id === s.rowId);
                if (s.status === 'done' &&
                    !confirm('Are you sure you want to delete?' +
                        (hasRow ? ' This also removes its row from the schedule.' : ''))) return;
                if (hasRow) {
                    removeRowAndScans(s.rowId); // removes this scan (and siblings) + the row
                } else {
                    const i = scans.indexOf(s);
                    if (i >= 0) scans.splice(i, 1);
                    FileStore.del(s.id);
                    syncScans();
                    renderScanList();
                }
            });
            item.appendChild(x);
        }
        list.appendChild(item);
    });
}

/* ==================== LEARNED RULES PANEL ==================== */

function renderLearningNote() {
    const wrap = $('learning-note');
    const list = $('learning-list');
    if (!wrap || !list) return;
    const items = [];

    Object.entries(Learning.data.labels).forEach(([field, arr]) => {
        arr.forEach(x => items.push(
            `Reads <b>"${esc(x.label)}"</b> as ${esc(FIELD_LABELS[field] || field)}` +
            (x.supplier ? ` on ${esc(x.supplier)} datasheets` : '')));
    });
    Object.entries(Learning.data.corrections).forEach(([k, to]) => {
        const [sup, field, from] = k.split('|');
        items.push(`Corrects ${esc(FIELD_LABELS[field] || field)} <b>"${esc(from.split('\n')[0])}"</b> to ` +
            `<b>"${esc(stripMd(to).split('\n')[0])}"</b>` + (sup !== 'ANY' ? ` for ${esc(sup)}` : ''));
    });

    wrap.classList.toggle('hidden', !items.length);
    list.innerHTML = items.map(t => `<div class="ln-item">${t}</div>`).join('');
}

/* ==================== SCAN ORCHESTRATION ==================== */

const FIELD_LABELS = {
    description: 'description', finish: 'finish', dimensions: 'dimensions', ip: 'IP',
    source: 'light source', cri: 'CRI', sdcm: 'SDCM', lifetime: 'lifetime',
    mounting: 'mounting', driver: 'driver', model: 'model'
};

async function scanFileIntoRow(file, targetRow) {
    let row = targetRow;
    if (!row) {
        row = blankRow();
        state.rows.push(row);
    }

    const scan = {
        id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
        name: file.name, pct: 0, status: 'busy', note: '', rowId: row.id
    };
    scans.unshift(scan);
    row.loading = { name: file.name, pct: 0 };
    FileStore.put(scan.id, file).catch(() => { /* storage unavailable - scan still works */ });
    renderBody();
    renderScanList();

    const setPct = (pct) => {
        scan.pct = pct;
        if (row.loading) row.loading.pct = pct;
        // update in place without a full re-render
        const tr = $('lfs-body').querySelector(`tr[data-id="${row.id}"]`);
        if (tr && tr.classList.contains('scanning-row')) {
            const bar = tr.querySelector('.scan-bar > div');
            const lbl = tr.querySelector('.scan-pct');
            if (bar) bar.style.width = pct + '%';
            if (lbl) lbl.textContent = pct + '%';
        }
        renderScanList();
    };

    try {
        let filled;
        if (/\.ies$/i.test(file.name)) {
            setPct(20);
            const text = await file.text();
            setPct(55);
            await tick(140);
            filled = iesIntoRow(row, file.name, text);
            setPct(100);
        } else {
            if (typeof pdfjsLib === 'undefined') throw new Error('PDF scanner unavailable (offline?)');
            filled = await pdfIntoRow(row, file, setPct);
        }
        await tick(200);
        row.scanned = true;
        row.loading = null;
        scan.status = 'done';
        let missing = SCAN_TARGET_KEYS.filter(k => !cellText(row, k));

        /* Ask the model only about what the rules could not find */
        if (missing.length) {
            let srcText = '';
            try { srcText = await FileStore.getText(row.id) || ''; } catch { /* none stored */ }
            const guessed = await LLM.fill(row, missing, srcText);
            if (guessed.length) {
                filled = filled.concat(guessed);
                missing = SCAN_TARGET_KEYS.filter(k => !cellText(row, k));
            }
        }

        scan.note = filled.length
            ? `Found ${filled.map(k => FIELD_LABELS[k] || k).join(', ')}`
            : 'No specs recognised';
        syncScans();
        persist();
        renderBody();   // repaints the row's datasheet link too
        renderScanList();
        autosizeAll();
        if (missing.length && filled.length) {
            toast(`${file.name}: ${filled.length} field${filled.length === 1 ? '' : 's'} filled - highlighted cells still need attention`, 3400);
        }
    } catch (e) {
        row.loading = null;
        if (!targetRow) state.rows = state.rows.filter(r => r.id !== row.id); // remove the row we created
        scan.status = 'error';
        scan.note = e.message;
        syncScans();
        renderBody();
        renderScanList();
        toast(`${file.name}: ${e.message}`, 3600);
    }
}

function tick(ms) { return new Promise(res => setTimeout(res, ms)); }

/* keep the finished scans (and their stored datasheets) across sessions */
function syncScans() {
    if (!state) return;
    state.scans = scans
        .filter(s => s.status !== 'busy')
        .slice(0, 50)
        .map(({ id, name, status, note, rowId }) => ({ id, name, status, note, rowId }));
    persist();
}

/* Delete a row and every scan/datasheet linked to it (both directions stay in sync) */
function removeRowAndScans(rowId) {
    state.rows = state.rows.filter(r => r.id !== rowId);
    for (let i = scans.length - 1; i >= 0; i--) {
        if (scans[i].rowId === rowId) {
            FileStore.del(scans[i].id);
            scans.splice(i, 1);
        }
    }
    syncScans();
    persist();
    renderBody();
    renderScanList();
}

function ingestFiles(fileList) {
    const files = [...fileList].filter(f => /\.(pdf|ies)$/i.test(f.name));
    if (!files.length) { toast('Drop .pdf datasheets or .ies files'); return; }
    files.forEach(f => scanFileIntoRow(f, null));
    showTab('schedule');
}

/* ==================== EXPORT ==================== */

function downloadBlob(blob, name) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

async function exportXlsx() {
    if (typeof ExcelJS === 'undefined') { toast('ExcelJS not loaded (offline?)'); return; }
    if (!state.rows.length) { toast('The schedule is empty - add a fitting first'); return; }
    if (COLS.every(c => colHidden(c.key))) { toast('All columns are hidden - show at least one to export'); return; }

    /* export exactly what is on screen: search-filtered rows, minus eye-hidden ones */
    const visibleRows = state.rows.filter(r => rowVisible(r));
    if (!visibleRows.length) { toast('No rows match the current search - nothing to export'); return; }
    if (visibleRows.every(r => r.hidden)) { toast('All visible rows are hidden - include at least one to export'); return; }

    const wb = buildWorkbook(ExcelJS, { ...state, rows: visibleRows });
    const buf = await wb.xlsx.writeBuffer();
    const base = (stripMd(state.title) || state.name || 'Light Fitting Schedule')
        .replace(/[^\w\- ]+/g, '').trim().replace(/ +/g, '-') || 'LFS';
    downloadBlob(new Blob([buf],
        { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), base + '.xlsx');
    toast('Exported ' + base + '.xlsx');
}

/* ==================== INIT ==================== */

let booted = false;

function initApp() {
    if (booted) return;   // DOMContentLoaded can fire twice; a second run would clobber saves
    booted = true;

    Learning.load();
    db = Store.load();
    db.projects.forEach(p => {
        if (!p.title || p.title === 'LIGHT FITTING SCHEDULE - ') p.title = 'LIGHT FITTING SCHEDULE';
    });
    useProject(db.currentId);

    /* projects */
    $('project-select').addEventListener('change', e => useProject(e.target.value));

    $('project-new').addEventListener('click', () => {
        const name = prompt('Name for the new project:', 'Project ' + (db.projects.length + 1));
        if (name === null) return;
        const p = newProject(name.trim() || 'Untitled project');
        db.projects.push(p);
        useProject(p.id);
        toast('Created "' + p.name + '"');
    });

    $('project-menu-btn').addEventListener('click', e => {
        e.stopPropagation();
        $('project-menu').classList.toggle('hidden');
    });
    $('project-menu').addEventListener('click', e => e.stopPropagation());

    $('project-rename').addEventListener('click', () => {
        $('project-menu').classList.add('hidden');
        const name = prompt('Rename project:', state.name);
        if (name === null) return;
        state.name = name.trim() || state.name;
        persist();
        renderProjectSelect();
    });

    $('project-duplicate').addEventListener('click', async () => {
        $('project-menu').classList.add('hidden');
        const copy = JSON.parse(JSON.stringify(cleanProject(state)));
        copy.id = newProject().id;
        copy.name = state.name + ' (copy)';
        /* give the copied datasheets their own ids + stored files */
        const idMap = {};
        for (const s of copy.scans) {
            const oldId = s.id;
            s.id = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
            idMap[oldId] = s.id;
            try {
                const blob = await FileStore.get(oldId);
                if (blob) await FileStore.put(s.id, blob);
            } catch { /* ignore */ }
        }
        const rowMap = {};
        copy.rows.forEach(r => {
            const oldRowId = r.id;
            r.id = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
            rowMap[oldRowId] = r.id;
        });
        copy.scans.forEach(s => { if (s.rowId && rowMap[s.rowId]) s.rowId = rowMap[s.rowId]; });
        db.projects.push(copy);
        useProject(copy.id);
        toast('Duplicated as "' + copy.name + '"');
    });

    $('project-delete').addEventListener('click', () => {
        $('project-menu').classList.add('hidden');
        if (db.projects.length <= 1) { toast('This is your only project - create another first'); return; }
        if (!confirm('Delete project "' + state.name + '" and its ' + state.rows.length +
            ' row(s) and datasheets? This cannot be undone.')) return;
        (state.scans || []).forEach(s => FileStore.del(s.id));
        db.projects = db.projects.filter(p => p.id !== state.id);
        useProject(db.projects[0].id);
        toast('Project deleted');
    });

    document.addEventListener('click', () => $('project-menu').classList.add('hidden'));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') $('project-menu').classList.add('hidden'); });

    /* tabs */
    $('tab-btn-datasheets').addEventListener('click', () => showTab('datasheets'));
    $('tab-btn-schedule').addEventListener('click', () => showTab('schedule'));

    /* title */
    $('schedule-title').addEventListener('input', e => { state.title = e.target.value.toUpperCase(); persist(); });

    /* search */
    $('global-search').addEventListener('input', e => { globalSearch = e.target.value.trim(); renderBody(); });
    $('scan-search').addEventListener('input', e => { scanSearch = e.target.value.trim(); renderScanList(); });

    renderLearningNote();
    $('learning-clear').addEventListener('click', () => {
        if (!confirm('Forget everything the scanner has learned from your corrections?')) return;
        Learning.clear();
        renderLearningNote();
        toast('Learned rules cleared');
    });

    /* filter button + panel */
    $('filter-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        const panel = $('filter-panel');
        const opening = panel.classList.contains('hidden');
        panel.classList.toggle('hidden');
        if (opening) renderFilterPanel();
    });
    $('filter-panel').addEventListener('click', e => e.stopPropagation());
    document.addEventListener('click', () => $('filter-panel').classList.add('hidden'));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') $('filter-panel').classList.add('hidden'); });
    $('filter-clear-all').addEventListener('click', () => {
        const anyHidden = COLS.some(c => colHidden(c.key));
        state.hiddenCols = {};
        if (!anyHidden) COLS.forEach(c => { state.hiddenCols[c.key] = true; }); // Hide all
        persist();
        renderHead();
        renderBody();
        autosizeAll();
        renderFilterBadge();
        renderFilterPanel();
    });

    /* add row */
    $('add-row-tr').addEventListener('click', () => {
        state.rows.push(blankRow());
        persist();
        renderBody();
        const trs = $('lfs-body').querySelectorAll('tr');
        const last = trs[trs.length - 1];
        if (last) { const c = last.querySelector('.cell'); if (c) c.focus(); }
    });
    /* add-row as drop target for new rows */
    const addTr = $('add-row-tr');
    addTr.addEventListener('dragover', e => {
        if (hasFiles(e)) { e.preventDefault(); e.stopPropagation(); addTr.classList.add('drop-target'); }
    });
    addTr.addEventListener('dragleave', () => addTr.classList.remove('drop-target'));
    addTr.addEventListener('drop', e => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        e.stopPropagation();
        addTr.classList.remove('drop-target');
        [...e.dataTransfer.files].filter(f => /\.(pdf|ies)$/i.test(f.name))
            .forEach(f => scanFileIntoRow(f, null));
    });

    /* export */
    $('export-xlsx').addEventListener('click', exportXlsx);

    /* big dropzone */
    const dz = $('big-dropzone');
    dz.addEventListener('click', () => $('file-input').click());
    $('browse-btn').addEventListener('click', e => { e.stopPropagation(); $('file-input').click(); });
    $('file-input').addEventListener('change', e => { ingestFiles(e.target.files); e.target.value = ''; });
    ['dragover', 'dragenter'].forEach(ev => dz.addEventListener(ev, e => {
        e.preventDefault();
        dz.classList.add('dragover');
    }));
    ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => {
        e.preventDefault();
        if (ev === 'dragleave' && dz.contains(e.relatedTarget)) return;
        dz.classList.remove('dragover');
    }));
    dz.addEventListener('drop', e => {
        if (e.dataTransfer.files.length) {
            const files = [...e.dataTransfer.files].filter(f => /\.(pdf|ies)$/i.test(f.name));
            if (!files.length) { toast('Drop .pdf datasheets or .ies files'); return; }
            files.forEach(f => scanFileIntoRow(f, null));
            renderScanList(); // stay on this tab; scans list shows progress
        }
    });

    /* window-level: prevent browser from opening dropped files */
    window.addEventListener('dragover', e => e.preventDefault());
    window.addEventListener('drop', e => e.preventDefault());

    /* auto-save to a project file */
    $('save-file').addEventListener('click', () => {
        if (ProjectFile.status === 'granted') { ProjectFile.write(); toast('Saved to ' + ProjectFile.handle.name); }
        else if (ProjectFile.status === 'prompt') ProjectFile.reconnect();
        else ProjectFile.link();
    });
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') ProjectFile.write(); // flush before the tab closes
    });
    ProjectFile.init();
}

/* ==================== PLEXUS TOOLS ACCESS CONTROL ==================== */

function showApp() {
    const mc = $('main-content');
    if (mc) mc.classList.remove('hidden');
    const ls = $('loading-screen');
    if (ls) {
        ls.style.opacity = '0';
        setTimeout(() => ls.classList.add('hidden'), 500);
    }
}

function grantAccess(user, initials, level, name, email, title, staffList) {
    sessionStorage.setItem('plexus-tools-access-granted', 'true');
    sessionStorage.setItem('plexus-user-name', name || user);
    sessionStorage.setItem('plexus-tools-access-granted-code', user);
    sessionStorage.setItem('plexus-user-initials', initials || '');
    sessionStorage.setItem('plexus-user-level', level || '3');
    sessionStorage.setItem('plexus-user-email', email || '');
    sessionStorage.setItem('plexus-user-title', title || '');
    if (staffList) sessionStorage.setItem('plexus-staff-list', JSON.stringify(staffList));
    showApp();
}

async function checkAuth() {
    // Local/dev use (opened directly from disk): skip Synergy auth
    if (location.protocol === 'file:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
        showApp();
        return;
    }
    try {
        const response = await fetch('../synergy.php?action=check', {
            method: 'GET',
            credentials: 'include'
        });
        const result = await response.json();
        if (result.success && result.user) {
            if (result.debug) console.log('Synergy Auth Debug:', result.debug);
            grantAccess(
                result.user.code,
                result.user.initials,
                result.user.level,
                result.user.name,
                result.user.email,
                result.user.title,
                result.debug ? result.debug.staff_list : null
            );
        } else {
            window.location.href = '../synergy.php?redirect=light-fitting-schedule/lfs.html';
        }
    } catch (error) {
        console.error('Error checking authentication:', error);
        window.location.href = '../synergy.php?redirect=light-fitting-schedule/lfs.html';
    }
}

if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', () => {
        initApp();
        checkAuth();
    });
}

/* Node test hook */
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        LLM, IES, buildWorkbook, COLS, blankRow, iesIntoRow, pdfIntoRow, modelCell, mdToRich, stripMd,
        detectDescription, detectMounting, detectDriver, detectSdcm, detectLifetime,
        detectDimensions, detectSupplier, describeFitting, labelValue, extractCct, extractLumens,
        extractWatts, extractCri, extractBeam, extractIp, extractFinish,
        extractDriver, categoryToMounting, categoryToDescription, dropOptionsColumn,
        extractIlluminance, hasLabel, stackedValue, scheduleCase, looksLikeFinish, titleLineParts, stripLanguageSuffix, linesFromTextContent,
        normDecimal, normThousands
    };
}
