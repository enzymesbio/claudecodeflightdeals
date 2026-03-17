/**
 * Import flight search results into Convex for persistent storage and comparison.
 *
 * Usage:
 *   1. Run: npx convex login
 *   2. Run: npx convex dev    (to deploy schema + functions)
 *   3. Run: node import_to_convex.js
 *
 * Or set CONVEX_URL env var and run directly.
 */

const { ConvexHttpClient } = require("convex/browser");
const fs = require("fs");
const path = require("path");

const CONVEX_URL = process.env.CONVEX_URL;
if (!CONVEX_URL) {
  console.error("Set CONVEX_URL environment variable first.");
  console.error("Steps:");
  console.error("  1. npx convex login");
  console.error("  2. npx convex dev   (deploys schema, gives you the URL)");
  console.error("  3. CONVEX_URL=https://your-project.convex.cloud node import_to_convex.js");
  process.exit(1);
}

const client = new ConvexHttpClient(CONVEX_URL);
const api = require("./convex/_generated/api");

async function importMassiveSearch() {
  const filePath = path.join(__dirname, "massive_search_results.json");
  if (!fs.existsSync(filePath)) {
    console.log("No massive_search_results.json found, skipping.");
    return;
  }

  const data = JSON.parse(fs.readFileSync(filePath, "utf-8"));
  const batchId = "massive_" + (data.generated || new Date().toISOString()).slice(0, 10);
  const searchDate = data.generated || new Date().toISOString();

  console.log(`Importing massive search: ${data.total_flights} flights...`);

  // Record the batch
  await client.mutation(api.flights.recordBatch, {
    batchId,
    searchDate,
    totalSearches: 588,
    totalFlights: data.total_flights || 0,
    dealsUnder2000: (data.under_2000_3pax || []).length,
    cheapestPrice: data.top50?.[0]?.price_pp || 0,
    cheapestRoute: data.top50?.[0]
      ? `${data.top50[0].origin}-${data.top50[0].destination}`
      : "unknown",
    notes: "588 searches across 6 origins, 4 destinations, May-Oct 2026",
  });

  // Import all flights in batches of 50 (Convex mutation size limit)
  const allFlights = data.all_flights || data.under_2000_3pax || data.top50 || [];
  const BATCH_SIZE = 50;

  for (let i = 0; i < allFlights.length; i += BATCH_SIZE) {
    const chunk = allFlights.slice(i, i + BATCH_SIZE).map((f) => ({
      origin: f.origin,
      destination: f.destination,
      departDate: f.depart_date,
      returnDate: f.return_date || undefined,
      tripDays: f.trip_days || undefined,
      pricePerPerson: f.price_pp,
      priceFamily: f.price_3pax,
      airline: f.airline,
      stops: f.stops,
      duration: f.duration || undefined,
      depTime: f.dep_time || undefined,
      arrTime: f.arr_time || undefined,
      depAirport: f.dep_airport || undefined,
      arrAirport: f.arr_airport || undefined,
      layovers: f.layovers || undefined,
      nonstop: f.stops === 0,
      searchDate,
      source: "google_flights",
      batchId,
    }));

    await client.mutation(api.flights.insertFlights, { flights: chunk });
    process.stdout.write(`  Imported ${Math.min(i + BATCH_SIZE, allFlights.length)}/${allFlights.length}\r`);
  }

  console.log(`\nDone: ${allFlights.length} flights imported as batch "${batchId}"`);

  // Also record price history for the cheapest routes
  const seen = new Set();
  for (const f of allFlights.slice(0, 100)) {
    const key = `${f.origin}-${f.destination}-${f.depart_date}-${f.airline}`;
    if (seen.has(key)) continue;
    seen.add(key);

    await client.mutation(api.flights.recordPrice, {
      origin: f.origin,
      destination: f.destination,
      departDate: f.depart_date,
      returnDate: f.return_date || undefined,
      airline: f.airline,
      price: f.price_pp,
      observedAt: searchDate,
      source: "google_flights",
    });
  }
  console.log(`Recorded price history for ${seen.size} unique routes.`);
}

async function importOtherResults() {
  const files = [
    { name: "pvg_comprehensive_results.json", label: "pvg_comprehensive" },
    { name: "rt_vs_ow_comparison.json", label: "rt_vs_ow" },
    { name: "best_deals_drilldown.json", label: "drilldown" },
    { name: "sichuan_results.json", label: "sichuan" },
  ];

  for (const { name, label } of files) {
    const filePath = path.join(__dirname, name);
    if (!fs.existsSync(filePath)) {
      console.log(`Skipping ${name} (not found)`);
      continue;
    }

    const data = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    const batchId = label + "_" + new Date().toISOString().slice(0, 10);
    const searchDate = new Date().toISOString();

    // Handle different JSON structures
    let flights = [];
    if (Array.isArray(data)) {
      flights = data;
    } else if (data.all_flights) {
      flights = data.all_flights;
    } else if (data.round_trips) {
      // rt_vs_ow format
      for (const rt of data.round_trips || []) {
        for (const f of rt.all_flights || []) {
          flights.push({
            origin: rt.origin,
            destination: rt.dest,
            depart_date: rt.dep_date,
            return_date: rt.ret_date,
            price_pp: f.price_pp,
            price_3pax: f.price_3pax,
            airline: f.airline,
            stops: f.stops,
            duration: f.duration,
          });
        }
      }
    } else if (data.top50) {
      flights = data.top50;
    }

    if (flights.length === 0) {
      console.log(`Skipping ${name} (no flights found in structure)`);
      continue;
    }

    console.log(`Importing ${name}: ${flights.length} flights...`);

    const BATCH_SIZE = 50;
    for (let i = 0; i < flights.length; i += BATCH_SIZE) {
      const chunk = flights.slice(i, i + BATCH_SIZE).map((f) => ({
        origin: f.origin || "???",
        destination: f.destination || f.dest || "???",
        departDate: f.depart_date || f.dep_date || f.departDate || "",
        returnDate: f.return_date || f.ret_date || f.returnDate || undefined,
        tripDays: f.trip_days || undefined,
        pricePerPerson: f.price_pp || f.pricePerPerson || 0,
        priceFamily: f.price_3pax || f.priceFamily || Math.round((f.price_pp || 0) * 2.75),
        airline: f.airline || "Unknown",
        stops: f.stops ?? 0,
        duration: f.duration || undefined,
        depTime: f.dep_time || undefined,
        arrTime: f.arr_time || undefined,
        depAirport: f.dep_airport || undefined,
        arrAirport: f.arr_airport || undefined,
        layovers: typeof f.layovers === "string" ? f.layovers : Array.isArray(f.layovers) ? f.layovers.join(", ") : undefined,
        nonstop: (f.stops ?? 0) === 0,
        searchDate,
        source: "google_flights",
        batchId,
      }));

      await client.mutation(api.flights.insertFlights, { flights: chunk });
    }

    console.log(`  Done: ${flights.length} flights as batch "${batchId}"`);
  }
}

async function main() {
  console.log("=== Importing Flight Data to Convex ===\n");
  console.log(`Convex URL: ${CONVEX_URL}\n`);

  await importMassiveSearch();
  await importOtherResults();

  console.log("\n=== All imports complete! ===");
  console.log("You can now query flights at your Convex dashboard.");
  console.log("Use compareBatches to track price changes between searches.");
}

main().catch((err) => {
  console.error("Import failed:", err);
  process.exit(1);
});
