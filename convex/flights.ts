import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Insert a batch of flight deals
export const insertFlights = mutation({
  args: {
    flights: v.array(v.object({
      origin: v.string(),
      destination: v.string(),
      departDate: v.string(),
      returnDate: v.optional(v.string()),
      tripDays: v.optional(v.number()),
      pricePerPerson: v.number(),
      priceFamily: v.number(),
      airline: v.string(),
      stops: v.number(),
      duration: v.optional(v.string()),
      depTime: v.optional(v.string()),
      arrTime: v.optional(v.string()),
      depAirport: v.optional(v.string()),
      arrAirport: v.optional(v.string()),
      layovers: v.optional(v.string()),
      nonstop: v.boolean(),
      searchDate: v.string(),
      source: v.string(),
      batchId: v.string(),
    })),
  },
  handler: async (ctx, args) => {
    const ids = [];
    for (const flight of args.flights) {
      const id = await ctx.db.insert("flights", flight);
      ids.push(id);
    }
    return { inserted: ids.length };
  },
});

// Record a search batch
export const recordBatch = mutation({
  args: {
    batchId: v.string(),
    searchDate: v.string(),
    totalSearches: v.number(),
    totalFlights: v.number(),
    dealsUnder2000: v.number(),
    cheapestPrice: v.number(),
    cheapestRoute: v.string(),
    notes: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("searchBatches", args);
  },
});

// Track price changes
export const recordPrice = mutation({
  args: {
    origin: v.string(),
    destination: v.string(),
    departDate: v.string(),
    returnDate: v.optional(v.string()),
    airline: v.string(),
    price: v.number(),
    observedAt: v.string(),
    source: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("priceHistory", args);
  },
});

// Get cheapest flights by route
export const cheapestByRoute = query({
  args: {
    origin: v.optional(v.string()),
    destination: v.optional(v.string()),
    maxPrice: v.optional(v.number()),
  },
  handler: async (ctx, args) => {
    let flights;
    if (args.origin && args.destination) {
      flights = await ctx.db
        .query("flights")
        .withIndex("by_route", (q) =>
          q.eq("origin", args.origin!).eq("destination", args.destination!)
        )
        .collect();
    } else if (args.origin) {
      flights = await ctx.db
        .query("flights")
        .withIndex("by_origin", (q) => q.eq("origin", args.origin!))
        .collect();
    } else {
      flights = await ctx.db.query("flights").collect();
    }

    if (args.maxPrice) {
      flights = flights.filter((f) => f.pricePerPerson <= args.maxPrice!);
    }

    flights.sort((a, b) => a.pricePerPerson - b.pricePerPerson);
    return flights.slice(0, 50);
  },
});

// Get all search batches
export const getBatches = query({
  handler: async (ctx) => {
    return await ctx.db
      .query("searchBatches")
      .withIndex("by_date")
      .order("desc")
      .collect();
  },
});

// Get price history for a route
export const getPriceHistory = query({
  args: {
    origin: v.string(),
    destination: v.string(),
    departDate: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("priceHistory")
      .withIndex("by_route_date", (q) =>
        q
          .eq("origin", args.origin)
          .eq("destination", args.destination)
          .eq("departDate", args.departDate)
      )
      .collect();
  },
});

// Compare prices between batches
export const compareBatches = query({
  args: {
    batchId1: v.string(),
    batchId2: v.string(),
  },
  handler: async (ctx, args) => {
    const batch1 = await ctx.db
      .query("flights")
      .withIndex("by_batch", (q) => q.eq("batchId", args.batchId1))
      .collect();
    const batch2 = await ctx.db
      .query("flights")
      .withIndex("by_batch", (q) => q.eq("batchId", args.batchId2))
      .collect();

    // Build route->price maps
    const priceMap1 = new Map<string, number>();
    const priceMap2 = new Map<string, number>();

    for (const f of batch1) {
      const key = `${f.origin}-${f.destination}-${f.departDate}-${f.airline}`;
      const existing = priceMap1.get(key);
      if (!existing || f.pricePerPerson < existing) {
        priceMap1.set(key, f.pricePerPerson);
      }
    }
    for (const f of batch2) {
      const key = `${f.origin}-${f.destination}-${f.departDate}-${f.airline}`;
      const existing = priceMap2.get(key);
      if (!existing || f.pricePerPerson < existing) {
        priceMap2.set(key, f.pricePerPerson);
      }
    }

    // Find price changes
    const changes = [];
    for (const [key, price1] of priceMap1) {
      const price2 = priceMap2.get(key);
      if (price2 !== undefined && price2 !== price1) {
        changes.push({
          route: key,
          oldPrice: price1,
          newPrice: price2,
          change: price2 - price1,
          changePercent: Math.round(((price2 - price1) / price1) * 100),
        });
      }
    }

    changes.sort((a, b) => a.change - b.change);
    return changes;
  },
});
