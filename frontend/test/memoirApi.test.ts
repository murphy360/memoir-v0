import assert from "node:assert/strict";
import { test } from "node:test";

import { apiBaseFrom, resolveApiUrl } from "../app/lib/memoirApi";

test("an absolute API URL wins over the base path", () => {
  assert.equal(
    apiBaseFrom("http://localhost:8001", "/memoir"),
    "http://localhost:8001",
  );
});

test("without an API URL the API is on the same origin under the base path", () => {
  assert.equal(apiBaseFrom("", "/memoir"), "/memoir");
  assert.equal(apiBaseFrom(undefined, "/memoir"), "/memoir");
});

test("with neither, API paths are relative to the origin's root", () => {
  assert.equal(apiBaseFrom(undefined, undefined), "");
  assert.equal(apiBaseFrom("", ""), "");
});

test("resolveApiUrl leaves absolute URLs alone and prefixes API paths", () => {
  assert.equal(
    resolveApiUrl("https://example.org/x.jpg"),
    "https://example.org/x.jpg",
  );
  assert.ok(resolveApiUrl("/api/health").endsWith("/api/health"));
});
