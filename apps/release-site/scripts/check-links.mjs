const site = process.env.VLADDER_SITE_URL ?? "https://vladder-release.vercel.app";
const timeoutMs = 15_000;

async function request(url) {
  const response = await fetch(url, {
    redirect: "follow",
    signal: AbortSignal.timeout(timeoutMs),
    headers: { "user-agent": "vladder-release-link-audit/1" },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.url}`);
  return response;
}

const page = await request(site);
const html = await page.text();
const links = [...new Set([...html.matchAll(/href="([^"]+)"/g)].map((match) => match[1]))];
const failures = [];

for (const href of links) {
  if (href.startsWith("#")) {
    const target = href.slice(1);
    if (!html.includes(`id="${target}"`)) failures.push(`${href}: missing page anchor`);
    continue;
  }
  const url = new URL(href, site).toString();
  try {
    const response = await request(url);
    console.log(`${href} -> ${response.status} ${response.url}`);
  } catch (error) {
    failures.push(`${href}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

if (failures.length > 0) {
  console.error(failures.join("\n"));
  process.exitCode = 1;
} else {
  console.log(`validated ${links.length} rendered links from ${site}`);
}
