<?php
/* ============================================================================
   llm-extract.php  -  datasheet reader for the Light Fitting Schedule

   WHY THIS FILE EXISTS
   The API key must never be in lfs.js. That file is downloaded by every
   browser that opens the tool, so a key in it is a published key. This script
   keeps the key on the server and is the only thing that talks to Anthropic.

   WHAT CHANGED (v2)
   This used to run last, on the handful of cells the regex scanner had left
   blank. It now runs FIRST, on every field, and the regex scanner backfills
   whatever the model declines to answer. A model reads a table it has never
   seen before; a regex only reads the tables someone thought to write a rule
   for. The rules stay because they are free, instant and deterministic, and
   because they are the fallback when this endpoint is unreachable.

   SETUP  (one time)
   1. Put the key in an environment variable on the web server:
          SetEnv ANTHROPIC_API_KEY sk-ant-...            (Apache .htaccess)
      or, if that is awkward, create a file OUTSIDE the web root:
          /etc/plexus/anthropic.key
      containing nothing but the key. Never put it inside the site folder.
   2. Drop this file next to lfs.html.
   3. That is all. If no key is found this returns 501 and the tool carries on
      exactly as it did before, rules only.

   WHAT IT SENDS
   Only the extracted TEXT of a supplier datasheet. No project names, no
   client names, no schedule contents.
   ========================================================================== */

declare(strict_types=1);
header('Content-Type: application/json');
header('X-Content-Type-Options: nosniff');

/* Model. Override per-server with ANTHROPIC_MODEL if you want to trial a
   different one without editing this file. Haiku is the right default: this
   is a reading-comprehension task over a short document with a fixed output
   shape, which is what the small model is good at, and a schematic-stage pack
   may run this a hundred times in an afternoon. */
const LLM_MODEL_DEFAULT = 'claude-haiku-4-5-20251001';
const LLM_MAX_TOKENS    = 1024;
const LLM_TEXT_LIMIT    = 24000;   // characters of datasheet text
const LLM_TIMEOUT       = 90;      // a PDF takes longer to read than a page of text
const LLM_MAX_REQUEST   = 20971520; // 20 MB of JSON, i.e. a ~15 MB datasheet

/* ---- who is allowed to spend money on the API ----------------------------
   Production: a Synergy session, the same gate as the rest of the site.
   Which key synergy.php actually sets has never been confirmed from this side,
   so several plausible names are accepted, and a refusal LOGS THE KEYS THAT
   WERE PRESENT. That turns a silent 401 - which looks identical to "the AI
   found nothing" from the browser - into a ten-second fix.

   Local: lfs.js already skips Synergy auth on localhost (see checkAuth), and
   this mirrors it. Both conditions must hold, loopback address AND an explicit
   LFS_DEV=1 in the server environment, so a production host can never fall
   through to it. dev-server.py is the easier local route and needs no PHP. */
session_start();

$signedIn = false;
foreach (['user','username','staff','staff_code','user_code','initials',
          'synergy_user','code'] as $k) {
    if (!empty($_SESSION[$k])) { $signedIn = true; break; }
}
$devMode = in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1','::1'], true)
        && getenv('LFS_DEV') === '1';

if (!$signedIn && !$devMode) {
    error_log('lfs-extract 401: no recognised session key. Present: '
        . (implode(',', array_keys($_SESSION)) ?: '(session empty)'));
    http_response_code(401);
    echo json_encode(['error' => 'Not signed in']);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'POST only']);
    exit;
}

/* ---- find the key ---- */
$key = getenv('ANTHROPIC_API_KEY') ?: '';
if ($key === '' && is_readable('/etc/plexus/anthropic.key')) {
    $key = trim((string)file_get_contents('/etc/plexus/anthropic.key'));
}
if ($key === '') {
    http_response_code(501);
    echo json_encode(['error' => 'No API key configured']);
    exit;
}

$model = getenv('ANTHROPIC_MODEL') ?: LLM_MODEL_DEFAULT;

/* Identity-linked API keys must name the workspace the request acts in, and
   are rejected with a 400 if they do not. Ordinary keys neither need nor want
   the header, so it is only sent when one is configured. Same two places as
   the key: an environment variable, or a file outside the web root. */
$workspace = getenv('ANTHROPIC_WORKSPACE_ID') ?: '';
if ($workspace === '' && is_readable('/etc/plexus/anthropic.workspace')) {
    $workspace = trim((string)file_get_contents('/etc/plexus/anthropic.workspace'));
}

/* ---- read and sanity-check the request ---- */
/* A base64 PDF is roughly 4/3 of the file, so the old 200 KB ceiling would
   reject almost every real datasheet. NOTE: PHP's own post_max_size caps this
   first - if large sheets 413 here, raise post_max_size in php.ini to match. */
$raw = file_get_contents('php://input');
if ($raw === false || strlen($raw) > LLM_MAX_REQUEST) {
    http_response_code(413);
    echo json_encode(['error' => 'Request too large']);
    exit;
}
$req    = json_decode($raw, true);
$fields = $req['fields'] ?? null;
$text   = $req['text'] ?? '';
$pdf    = $req['pdf']  ?? '';          // base64 of the original PDF, if sent
if (!is_string($pdf) || !preg_match('#^[A-Za-z0-9+/=]*$#', $pdf)) $pdf = '';
if (!is_array($fields) || !$fields || !is_string($text)
    || (trim($text) === '' && $pdf === '')) {
    http_response_code(400);
    echo json_encode(['error' => 'Nothing to extract']);
    exit;
}

/* Only ever ask about columns the tool actually has. Anything else is
   ignored, so a tampered request cannot turn this into a general chatbot. */
/* 'manufacturer' and 'code' are not columns: they are the second and third
   lines of the MANUFACTURER / MODEL cell. */
$allowed = ['description','finish','dimensions','ip','source','cri',
            'sdcm','lifetime','mounting','driver','model',
            'manufacturer','code'];
$fields = array_intersect_key($fields, array_flip($allowed));
if (!$fields) {
    http_response_code(400);
    echo json_encode(['error' => 'No valid fields requested']);
    exit;
}

$text = mb_substr($text, 0, LLM_TEXT_LIMIT);

/* ---- the prompt ----
   The instruction that matters most is the one about UNKNOWN. A blank cell
   the engineer fills in is cheap and the tool highlights it in yellow until
   they do. A plausible wrong number that reaches a construction drawing is
   not cheap, and nothing downstream will catch it.

   The second thing that matters is the multi-variant rule. Supplier sheets
   are usually written for a product FAMILY: one PDF covering four colour
   temperatures, three drive currents and six finishes. Picking one of those
   is a specification decision belonging to the engineer, not a reading
   comprehension task. Where the sheet offers a choice, the honest answer is
   no answer. */

/* The prompt lives in extract-prompt.md, which dev-server.py reads too, so
   the thing you test locally and the thing that runs in production cannot
   drift apart. Edit the prompt there, never here. */
$promptFile = __DIR__ . '/extract-prompt.md';
if (!is_readable($promptFile)) {
    http_response_code(500);
    echo json_encode(['error' => 'extract-prompt.md is missing beside llm-extract.php']);
    exit;
}
/* Discard the comment header: every line before the first marker LINE.
   Searching for the marker text instead would match a mention of it in the
   comments - which it did, and the model got the comments as its system
   prompt. */
$lines = preg_split('/\R/', (string)file_get_contents($promptFile));
while ($lines && strncmp($lines[0], '===', 3) !== 0) array_shift($lines);
$parts  = explode('===SYSTEM===', implode("\n", $lines), 2);
$halves = isset($parts[1]) ? explode('===USER===', $parts[1], 2) : [];
if (count($halves) !== 2) {
    http_response_code(500);
    echo json_encode(['error' => 'extract-prompt.md has lost its ===SYSTEM=== / ===USER=== markers']);
    exit;
}
$system = trim($halves[0]);

$wanted = '';
foreach ($fields as $k => $desc) {
    $wanted .= "  \"$k\": " . (is_string($desc) ? $desc : '') . "\n";
}
/* Send the PDF itself when we have it. Flattening a datasheet to text
   destroys what tells a reader which number belongs to which label, and leaves
   every decoy behind - "Luminous Length 628mm" reads exactly like
   "Dimensions 650mm" once the panels are gone, and a dimension drawn on a
   diagram does not survive at all. Text remains the fallback. */
const ATTACHED = 'The datasheet is attached to this message as a PDF. Read it as '
    . 'a page: use the table columns, the panel each value sits in, and the '
    . 'dimension drawings. Do not rely on reading order alone.';

$prompt = str_replace(
    ['{{FIELDS}}', '{{TEXT}}'],
    [$wanted, $pdf !== '' ? ATTACHED : $text],
    trim($halves[1])
);

if ($pdf !== '') {
    /* document block first - Anthropic's guidance for extraction accuracy */
    $userContent = [
        ['type' => 'document',
         'source' => ['type' => 'base64', 'media_type' => 'application/pdf', 'data' => $pdf]],
        ['type' => 'text', 'text' => $prompt]
    ];
} else {
    $userContent = $prompt;
}

$payload = json_encode([
    'model'       => $model,
    'max_tokens'  => LLM_MAX_TOKENS,
    'temperature' => 0,
    'system'      => $system,
    'messages'    => [
        ['role' => 'user',      'content' => $userContent],
        /* Prefilling the opening brace removes the whole class of failure
           where the model wraps the object in prose or a code fence. */
        ['role' => 'assistant', 'content' => '{']
    ]
]);

/* ---- call the API ---- */
$started = microtime(true);
$ch = curl_init('https://api.anthropic.com/v1/messages');
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_POST           => true,
    CURLOPT_POSTFIELDS     => $payload,
    CURLOPT_TIMEOUT        => LLM_TIMEOUT,
    CURLOPT_HTTPHEADER     => array_filter([
        'Content-Type: application/json',
        'x-api-key: ' . $key,
        'anthropic-version: 2023-06-01',
        $workspace !== '' ? 'anthropic-workspace-id: ' . $workspace : null
    ])
]);
$body = curl_exec($ch);
$code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$err  = curl_error($ch);
curl_close($ch);

if ($body === false || $code !== 200) {
    /* Pass the API's own message through. A 400 saying 'anthropic-workspace-id
       is required' is a five-minute fix; 'Upstream failed' is an afternoon. */
    $why = $err ?: mb_substr((string)$body, 0, 400);
    error_log('lfs-extract upstream ' . $code . ': ' . $why);
    http_response_code(502);
    echo json_encode(['error' => 'Upstream failed', 'status' => $code, 'detail' => $why]);
    exit;
}

$out     = json_decode($body, true);
$content = $out['content'][0]['text'] ?? '';

/* We prefilled '{', so the reply is the remainder of the object. */
$content = '{' . $content;

$vals = json_decode($content, true);
if (!is_array($vals)) {
    /* Belt and braces: strip a code fence, then take the outermost {...}. */
    $stripped = trim(preg_replace('/^```(?:json)?|```$/m', '', $content));
    $vals = json_decode($stripped, true);
    if (!is_array($vals) && preg_match('/\{.*\}/s', $stripped, $m)) {
        $vals = json_decode($m[0], true);
    }
}
if (!is_array($vals)) {
    http_response_code(502);
    echo json_encode([
        'error'  => 'Could not read the model response',
        'sample' => mb_substr($content, 0, 200)
    ]);
    exit;
}

/* Hand back only the requested keys, as strings, trimmed and length-capped.
   UNKNOWN and its lookalikes are dropped here rather than in the browser, so
   the client only ever sees values it can use. */
$clean = [];
$sources = [];
$blank = '/^(unknown|n\/?a|none|null|not stated|not specified|-+)$/i';
foreach (array_keys($fields) as $k) {
    $raw = $vals[$k] ?? null;

    /* Shape: {"n": <how many values the sheet offers>, "v": <value>, "src": <quote>}
       The count is ENFORCED here rather than trusted. A field the sheet gives
       two values for is blanked however confidently v was filled in - asking
       the model to remember the rule was not reliable; asking it to show the
       count and applying the rule in code is. */
    if (is_array($raw)) {
        $n = isset($raw['n']) && is_numeric($raw['n']) ? (int)$raw['n'] : -1;
        $v = isset($raw['v']) && is_string($raw['v']) ? trim($raw['v']) : '';
        if ($n !== 1 || $v === '' || preg_match($blank, $v)) continue;
        $src = (isset($raw['src']) && is_string($raw['src'])) ? trim($raw['src']) : '';
        /* The quote can convict the value. If the only evidence offered is an
           availability line, this is an option the product CAN have rather than
           what it IS - the "Dali Available: Yes" case. A legitimate source quote
           does not need these words. */
        if ($src !== '' && preg_match('/\b(available|optional|on request|can be supplied|upon request)\b/i', $src)) {
            continue;
        }
        $clean[$k] = mb_substr($v, 0, 120);
        if ($src !== '') $sources[$k] = mb_substr($src, 0, 160);
        continue;
    }

    /* Older shape: a bare string. Still accepted. */
    if (!is_string($raw)) continue;
    $v = trim($raw);
    if ($v === '' || preg_match($blank, $v)) continue;
    $clean[$k] = mb_substr($v, 0, 120);
}
if ($sources) $clean['_src'] = $sources;

/* One line per scan, so cost and hit-rate can be reviewed later without
   keeping any of the datasheet itself. */
$usage = $out['usage'] ?? [];
error_log(sprintf(
    'lfs-extract model=%s input=%s in=%d out=%d asked=%d filled=%d ms=%d',
    $model,
    $pdf !== '' ? 'pdf' : 'text',
    $usage['input_tokens']  ?? 0,
    $usage['output_tokens'] ?? 0,
    count($fields),
    count($clean) - (isset($clean['_src']) ? 1 : 0),
    (int)round((microtime(true) - $started) * 1000)
));

echo json_encode($clean);
