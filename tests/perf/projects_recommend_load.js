// k6 script: basic load test for /projects/recommend
// Usage: k6 run tests/perf/projects_recommend_load.js
import http from 'k6/http';
import { sleep } from 'k6';

export let options = {
  vus: 20,
  duration: '1m'
};

export default function () {
  const url = `http://${__ENV.HOSTNAME || '127.0.0.1'}:8000/projects/recommend`;
  const payload = JSON.stringify({ query: 'desarrollo API ejemplo', top_k: 5 });
  const params = { headers: { 'Content-Type': 'application/json' } };
  const res = http.post(url, payload, params);
  // record simple checks
  // error rate visible by non-200 responses
  // k6 will print metrics after run
  sleep(1);
}
