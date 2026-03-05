export async function onRequest(context) {
  const url = new URL(context.request.url);
  const ocmUrl = 'https://api.openchargemap.io/v3/poi/' + url.search;

  const resp = await fetch(ocmUrl, {
    headers: { 'User-Agent': 'laadpalenwijchen.nl/1.0' },
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
