// The bundle's entry point: find the island the page drew, and take it over.
//
// The page (templates/results.html) has already drawn everything inside
// #topic-island from the same data it embeds in #topic-island-data. This
// hands that data to the component, which draws the same thing and from then
// on swaps the five when a topic is chosen (ADR 0025).
//
// If either element is missing -- a page without the island, an error page --
// this does nothing, and nothing on the page depends on it having run.

import { createRoot } from 'react-dom/client'
import TopicIsland from './TopicIsland.jsx'

const root = document.getElementById('topic-island')
const blob = document.getElementById('topic-island-data')

if (root && blob) {
  createRoot(root).render(<TopicIsland initial={JSON.parse(blob.textContent)} />)
}
