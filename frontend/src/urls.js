// The two addresses a topic has. `urls` comes from the page (web.island_data),
// so these only add the ?topic= part and never build a route themselves.

// The page for a topic's list, or the overall five for none.
export function pageUrl(urls, topic) {
  return topic ? `${urls.results}?topic=${encodeURIComponent(topic)}` : urls.results
}

// The same list as data, for the component to swap in.
export function dataUrl(urls, topic) {
  return topic ? `${urls.recommendations}?topic=${encodeURIComponent(topic)}` : urls.recommendations
}
