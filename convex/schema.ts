import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  // Each flight deal found by the scraper
  flights: defineTable({
    origin: v.string(),           // IATA code: ICN, HKG, PVG, etc.
    destination: v.string(),      // IATA code: LAX, SFO, SEA, etc.
    departDate: v.string(),       // "2026-05-15"
    returnDate: v.optional(v.string()), // null for one-way
    tripDays: v.optional(v.number()),
    pricePerPerson: v.number(),   // USD round-trip per person
    priceFamily: v.number(),      // estimated 3-pax (price * 2.75)
    airline: v.string(),
    stops: v.number(),
    duration: v.optional(v.string()),
    depTime: v.optional(v.string()),
    arrTime: v.optional(v.string()),
    depAirport: v.optional(v.string()),
    arrAirport: v.optional(v.string()),
    layovers: v.optional(v.string()),
    nonstop: v.boolean(),
    // Metadata
    searchDate: v.string(),       // when this was scraped
    source: v.string(),           // "google_flights", "ita_matrix", etc.
    batchId: v.string(),          // group searches together
  })
    .index("by_origin", ["origin"])
    .index("by_destination", ["destination"])
    .index("by_price", ["pricePerPerson"])
    .index("by_route", ["origin", "destination"])
    .index("by_airline", ["airline"])
    .index("by_batch", ["batchId"])
    .index("by_search_date", ["searchDate"]),

  // Price history: track how prices change over time
  priceHistory: defineTable({
    origin: v.string(),
    destination: v.string(),
    departDate: v.string(),
    returnDate: v.optional(v.string()),
    airline: v.string(),
    price: v.number(),
    observedAt: v.string(),       // ISO timestamp
    source: v.string(),
  })
    .index("by_route_date", ["origin", "destination", "departDate"])
    .index("by_observed", ["observedAt"]),

  // Search batches for tracking
  searchBatches: defineTable({
    batchId: v.string(),
    searchDate: v.string(),
    totalSearches: v.number(),
    totalFlights: v.number(),
    dealsUnder2000: v.number(),
    cheapestPrice: v.number(),
    cheapestRoute: v.string(),
    notes: v.optional(v.string()),
  })
    .index("by_date", ["searchDate"])
    .index("by_batch", ["batchId"]),
});
