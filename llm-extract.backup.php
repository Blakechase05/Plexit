<?php
/* ============================================================================
   llm-extract.php  -  server-side gap filler for the Light Fitting Schedule

   WHY THIS FILE EXISTS
   The API key must never be in lfs.js. That file is downloaded by every
   browser that opens the tool, so a key in it is a published key. This script
   keeps the key on the server and is the only thing that talks to Anthropic.

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
   Only the extracted TEXT of a supplier datasheet, and only the fields the
   rule-based scanner failed to find. No project names, no client names, no
   schedule contents.
   ========================================================================== */

declare(strict_types=1);
header('Content-Type: application/json');
header('X-Content-Type-Options: nosniff');

/* ---- only logged-in Plexus users, same gate as the rest of the site ---- */
session_start();
if (empty($_SESSION['user']) && empty($_SESSION['username'])) {
    /* Adjust this check if synergy.php stores the user under another key.
       Failing closed is deliberate: no session, no API spend. */
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

/* ---- read and sanity-check the request ---- */
$raw = file_get_contents('php://input');
if ($raw === false || strlen($raw) > 200000) {
    http_response_code(413);
    echo json_encode(['error' => 'Request too large']);
    exit;
}
$req = json_decode($raw, true);
$fields = $req['fields'] ?? null;
$text   = $req['text'] ?? '';
if (!is_array($fields) || !$fields || !is_string($text) || trim($text) === '') {
    http_response_code(400);
    echo json_encode(['error' => 'Nothing to extract']);
    exit;
}

/* Only ever ask about columns the tool actually has. Anything else is
   ignored, so a tampered request cannot turn this into a general chatbot. */
$allowed = ['description','finish','dimensions','ip','source','cri',
            'sdcm','lifetime','mounting','driver','model'];
$fields = array_intersect_key($fields, array_flip($allowed));
if (!$fields) {
    http_response_code(400);
    echo json_encode(['error' => 'No valid fields requested']);
    exit;
}

$text = mb_substr($text, 0, 24000);

/* ---- build the prompt ----
   The instruction that matters most is the last one: answering UNKNOWN is a
   correct answer. A blank cell the engineer fills in is cheap; a plausible
   wrong number that reaches a construction drawing is not. */
$wanted = '';
foreach ($fields as $k => $desc) {
    $wanted .= "- \"$k\": " . (is_string($desc) ? $desc : '') . "\n";
}

$prompt = <<<TXT
Below is the text of a lighting product datasheet, extracted from a PDF.

Return a JSON object containing ONLY these keys:
$wanted
Rules:
- Use ONLY what is stated in the datasheet. Never infer, never estimate,
  never use general knowledge about the manufacturer.
- If a value is not clearly stated, set that key to "UNKNOWN".
- If the sheet offers several options (for example a table of variants, or
  "Recessed / Surface"), that is not a single value: answer "UNKNOWN".
- Ignore packaging dimensions, carton sizes, cut-out sizes and bend radii.
- Answer with the JSON object and nothing else. No explanation, no markdown.

DATASHEET
---------
$text
TXT;

$payload = json_encode([
    'model'       => 'claude-sonnet-5',
    'max_tokens'  => 700,
    'temperature' => 0,
    'messages'    => [['role' => 'user', 'content' => $prompt]]
]);

/* ---- call the API ---- */
$ch = curl_init('https://api.anthropic.com/v1/messages');
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_POST           => true,
    CURLOPT_POSTFIELDS     => $payload,
    CURLOPT_TIMEOUT        => 45,
    CURLOPT_HTTPHEADER     => [
        'Content-Type: application/json',
        'x-api-key: ' . $key,
        'anthropic-version: 2023-06-01'
    ]
]);
$body = curl_exec($ch);
$code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$err  = curl_error($ch);
curl_close($ch);

if ($body === false || $code !== 200) {
    http_response_code(502);
    echo json_encode(['error' => 'Upstream failed', 'status' => $code, 'detail' => $err]);
    exit;
}

$out = json_decode($body, true);
$content = $out['content'][0]['text'] ?? '';

/* The model was asked for bare JSON, but strip a code fence just in case. */
$content = trim(preg_replace('/^```(?:json)?|```$/m', '', $content));
$vals = json_decode($content, true);
if (!is_array($vals)) {
    http_response_code(502);
    echo json_encode(['error' => 'Could not read the model response']);
    exit;
}

/* Hand back only the requested keys, as strings, trimmed and length-capped. */
$clean = [];
foreach (array_keys($fields) as $k) {
    if (!isset($vals[$k]) || !is_string($vals[$k])) continue;
    $v = trim($vals[$k]);
    if ($v === '' || strcasecmp($v, 'UNKNOWN') === 0) continue;
    $clean[$k] = mb_substr($v, 0, 120);
}

echo json_encode($clean);
