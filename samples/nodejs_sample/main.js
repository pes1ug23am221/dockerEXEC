// Node.js sample: reads CSV data, computes stats, writes output
const fs = require("fs");
const path = require("path");

const { mean, median } = require("simple-statistics");

// Generate some numbers
const data = Array.from({ length: 20 }, (_, i) => (i + 1) * 3.14);

console.log("=== Node.js Statistics Sample ===");
console.log(`Input data (${data.length} values):`, data.map(v => v.toFixed(2)).join(", "));
console.log(`Mean   : ${mean(data).toFixed(4)}`);
console.log(`Median : ${median(data).toFixed(4)}`);
console.log(`Min    : ${Math.min(...data).toFixed(4)}`);
console.log(`Max    : ${Math.max(...data).toFixed(4)}`);

// Write result to file
const output = {
  count: data.length,
  mean: mean(data),
  median: median(data),
  min: Math.min(...data),
  max: Math.max(...data),
  generated_at: new Date().toISOString(),
};

fs.writeFileSync("output.json", JSON.stringify(output, null, 2));
console.log("\n[Done] Results written to output.json");
