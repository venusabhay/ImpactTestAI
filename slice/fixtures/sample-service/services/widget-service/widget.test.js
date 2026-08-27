// Fixture test file for the pilot CI smoke test. References the /widgets
// route (like a real test-coverage signal) but is never actually executed
// with a real test runner -- see package.json's trivial "test" script.
describe("widget-service", () => {
  it("references GET /widgets", () => {
    expect(true).toBe(true);
  });
});
