export async function onRequest(context) {
  const apiKey = context.env.OCM_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: 'OCM_API_KEY not configured' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const url = new URL(context.request.url);
  url.searchParams.delete('key');
  const ocmUrl = 'https://api.openchargemap.io/v3/poi/' + url.search;

  const resp = await fetch(ocmUrl, {
    headers: {
      'User-Agent': 'laadpalenwijchen.nl/1.0',
      'X-API-Key': apiKey,
    },
  });

  return new Response(resp.body, {
    status: resp.status,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': 'public, max-age=300',
    },
  });
}
