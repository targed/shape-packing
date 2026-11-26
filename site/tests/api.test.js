// site/tests/api.test.js
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  fetchClusterStats,
  fetchLeaderboard,
  fetchRecentSolutions,
  validateCoordinatorUrl,
} from '../src/lib/api.js';

describe('Coordinator API Client', () => {
  it('parses cluster stats response correctly', async () => {
    const mockFetch = async () => ({
      ok: true,
      json: async () => ({
        total_problems: 2249,
        active_workers: 4,
        total_cluster_attempts: 125000,
        total_records_broken: 3,
        total_workers: 5,
      }),
    });

    const result = await fetchClusterStats('http://localhost:8000', mockFetch);
    assert.equal(result.ok, true);
    assert.equal(result.data.active_workers, 4);
    assert.equal(result.data.total_attempts, 125000);
    assert.equal(result.data.records_broken, 3);
  });

  it('handles server offline gracefully with fallback status', async () => {
    const mockFailingFetch = async () => {
      throw new Error('Connection refused');
    };

    const result = await fetchClusterStats('http://localhost:8000', mockFailingFetch);
    assert.equal(result.ok, false);
    assert.match(result.error, /Connection refused/);
  });

  it('parses leaderboard rankings correctly', async () => {
    const mockFetch = async () => ({
      ok: true,
      json: async () => ([
        { username: 'targed', total_attempts: 90000, records_broken: 2 },
        { username: 'worker-beta', total_attempts: 35000, records_broken: 1 },
      ]),
    });

    const result = await fetchLeaderboard('http://localhost:8000', mockFetch);
    assert.equal(result.ok, true);
    assert.equal(result.data.length, 2);
    assert.equal(result.data[0].username, 'targed');
    assert.equal(result.data[0].records_broken, 2);
  });

  it('parses recent solutions correctly', async () => {
    const mockFetch = async () => ({
      ok: true,
      json: async () => ([
        {
          id: 116,
          problem_id: '21_dominhex',
          n: 21,
          inner_token: 'DOMINO',
          container_token: '6',
          metric_s: 4.517339,
          reference_s: 4.5981,
          diff: -0.080761,
          is_current_record: true,
          worker_username: 'web_volunteer',
          verified_at: '2026-11-22 00:01:44',
        },
      ]),
    });

    const result = await fetchRecentSolutions(10, 'http://localhost:8000', mockFetch);
    assert.equal(result.ok, true);
    assert.equal(result.data.length, 1);
    assert.equal(result.data[0].problem_id, '21_dominhex');
    assert.equal(result.data[0].metric_s, 4.517339);
    assert.equal(result.data[0].worker_username, 'web_volunteer');
    assert.equal(result.data[0].is_current_record, true);
  });

  it('allows only official coordinator origins for query overrides and rejects unsafe schemes', () => {
    assert.equal(
      validateCoordinatorUrl('https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net/'),
      'https://shape-packing-ggd4d5e8c2ctggam.eastus-01.azurewebsites.net'
    );
    assert.equal(validateCoordinatorUrl('http://localhost:8000/api'), 'http://localhost:8000');
    assert.equal(validateCoordinatorUrl('https://evil.example.com'), null);
    assert.equal(validateCoordinatorUrl('javascript:alert(1)', { allowCustomHttps: true }), null);
    assert.equal(validateCoordinatorUrl('http://evil.example.com', { allowCustomHttps: true }), null);
    assert.equal(validateCoordinatorUrl('https://user:pass@custom.example.com', { allowCustomHttps: true }), null);
    assert.equal(validateCoordinatorUrl('https://custom.example.com/path', { allowCustomHttps: true }), 'https://custom.example.com');
  });
});
