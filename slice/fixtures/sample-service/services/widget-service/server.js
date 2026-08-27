// Minimal, dependency-free fixture used only by the pilot CI smoke test
// (.github/workflows/pilot-ci.yml). Not a real service -- it exists so
// analyze_change.py can be exercised end-to-end in CI without depending
// on any external repository or network access.
const express = require("express");
const app = express();

app.get("/widgets", (req, res) => {
  res.json({ widgets: [] });
});

const PORT = process.env.PORT || 3999;
app.listen(PORT, () => console.log(`widget-service fixture running on ${PORT}`));
