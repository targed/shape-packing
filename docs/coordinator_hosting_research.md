# Coordinator Server Hosting Research

Investigation of hosting options for the Distributed Shape Packing Coordinator (`src/shape_packing/server/app.py`) alongside the existing GitHub Pages frontend.

## 1. Application Constraints (Observed in Codebase)

1. **Compute and storage model:** FastAPI + Uvicorn + local SQLite WAL file (`shape_packing.db` + `data/packingVerification/*.json`).
2. **Memory footprint:** Measured at `88.9 MB` RSS on startup (`create_app` loading `numpy`, `scipy`, `matplotlib`, `numba`, `fastapi`, `catalog`). Fits comfortably in `512 MB - 1 GB` RAM.
3. **Why GitHub Pages cannot host the coordinator:** GitHub Pages only serves static files (`site/dist/`) over HTTPS. It cannot run Python (`uvicorn`) or accept `POST /api/v1/solutions` writes to SQLite.
4. **HTTPS Mixed-Content requirement:** Because GitHub Pages is served over HTTPS, browsers block `fetch()` calls from `https://*.github.io` to plain `http://` coordinator URLs (only `http://localhost` is exempted). Any public coordinator must terminate TLS (`https://api.<domain>`).
5. **Current frontend default:** `site/src/lib/api.ts` and `site/src/pages/contribute.astro` currently default to `http://localhost:8000` unless overridden by `?coordinator=` or `localStorage`.

## 2. Hosting Options Compared

| Option | Cost | Persistence (`shape_packing.db`) | Card Needed? | Key Catch |
| :--- | :--- | :--- | :--- | :--- |
| **Home / Dorm Machine + Cloudflare Tunnel** | \$0 forever | Full local disk | No | Goes offline if the machine sleeps or loses internet |
| **Oracle Cloud Always Free** (`VM.Standard.A1.Flex` or `E2.1.Micro`) | \$0 forever | Full 200 GB block storage | Yes (identity check) | Reclaims idle VMs if CPU stays below ~10-15% for 7 days; A1 ARM capacity can be scarce |
| **Azure for Students** (`B1s` Linux VM) | \$0 for active student term (12 mo cycle, \$100 credit) | Managed OS disk (Standard SSD/HDD) | No | Account/credits expire in ~115 days unless renewed via school verification |
| **Railway Free Tier** | \$0 (`$1/mo` usage grant) | 0.5 GB persistent Volume | No | Sleeps after 5-10 min outbound inactivity; active worker polling burns `$1` credit quickly |
| **Render / Koyeb Free Tier** | \$0 | Ephemeral disk only | Koyeb: Yes (`$29` auth hold) | **Wipes `shape_packing.db`** on every sleep or redeploy |
| **Fly.io** | ~\$2.19+/mo | Paid volumes | Yes | No permanent free tier for new accounts |

## 3. Domain Name Caveat (GitHub Student Pack `.tech`)

- The GitHub Student Developer Pack provides a free `.tech` domain for Year 1.
- Standard `.tech` renewals in Year 2 typically cost \$40-\$50+/year. If keeping the project alive long-term at minimal cost, plan either to buy an inexpensive domain on Cloudflare Registrar (at-cost renewal, ~\$10/yr for `.com`/`.org`) or switch before Year 2 renewal (or run a free subdomain like a Cloudflare Tunnel URL or DuckDNS if a custom domain is not needed).

## 4. Sources

- Microsoft Azure for Students free services & credits: [Azure for Students](https://azure.microsoft.com/en-us/free/students/) (750 hrs/mo `B1s` VM for 12 months, \$100 credit, no card required).
- Oracle Cloud Always Free compute & block storage: [OCI Free Tier](https://www.oracle.com/cloud/free/) (Always Free `VM.Standard.A1.Flex` up to 2 OCPUs / 12 GB RAM free pool + 2 AMD micro VMs + 200 GB block storage).
- Cloudflare Zero Trust Tunnels: [Cloudflare Tunnel Docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (outbound-only daemon `cloudflared`, free TLS termination without port forwarding).
- Railway / Render / Koyeb free-tier volume and sleep policies: [Railway Pricing](https://railway.com/pricing), [Render Free Tier](https://render.com/docs/free), [Koyeb Pricing](https://www.koyeb.com/pricing).
