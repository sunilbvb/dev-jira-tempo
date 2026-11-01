/**
 * timeline.js - Interactive Day Timeline and Auto-Scheduler Module
 * Follows vanilla JS single-responsibility modular structure.
 */

export class TimelineModule {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.currentDate = new Date().toISOString().split('T')[0];
    this.scheduledItems = [];
    this.init();
  }

  init() {
    if (!this.container) return;
    this.render();
    this.attachEvents();
  }

  render() {
    this.container.innerHTML = `
      <div class="ui-card" style="background: var(--ui-bg-surface); border: 1px solid var(--ui-border-color); border-radius: 12px; padding: 20px;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; flex-wrap: wrap; gap: 10px;">
          <div style="font-size: 16px; font-weight: 600; color: #f8fafc;">📅 Interactive Day Timeline &amp; Auto-Scheduler</div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <input id="timeline-date-picker" class="ui-input" type="date" value="${this.currentDate}" style="padding: 4px 8px; font-size: 13px;">
            <button id="btn-run-schedule" class="ui-button ui-button-primary" style="font-size: 12px; padding: 6px 12px;">⚡ Auto-Schedule</button>
            <button id="btn-export-html" class="ui-button ui-button-secondary" style="font-size: 12px; padding: 6px 12px;">🖨 Printable HTML</button>
          </div>
        </div>

        <div style="margin-bottom: 12px;">
          <textarea id="timeline-journal-input" class="ui-input" rows="3" placeholder="Paste journal notes or 'Time: 10:00-11:00 (1h) | Ticket: PROJ-101' markdown here to schedule..." style="width: 100%; font-family: monospace; font-size: 12px;"></textarea>
        </div>

        <div id="timeline-visual-bar" style="background: rgba(15, 23, 42, 0.6); border: 1px solid var(--ui-border-color); border-radius: 8px; padding: 12px; min-height: 80px; position: relative; margin-bottom: 14px; overflow-x: auto;">
          <div style="color: #64748b; font-size: 13px; text-align: center; padding: 20px;">
            Click <strong>⚡ Auto-Schedule</strong> to generate timeline blocks.
          </div>
        </div>

        <div id="timeline-details-table" style="font-size: 12px; color: #94a3b8;">
          <!-- Populated when scheduled -->
        </div>
      </div>
    `;
  }

  attachEvents() {
    const runBtn = document.getElementById('btn-run-schedule');
    const dateInput = document.getElementById('timeline-date-picker');
    const exportBtn = document.getElementById('btn-export-html');

    if (dateInput) {
      dateInput.addEventListener('change', (e) => {
        this.currentDate = e.target.value;
      });
    }

    if (runBtn) {
      runBtn.addEventListener('click', () => this.autoSchedule());
    }

    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        window.open(`/api/export?format=html&from=${this.currentDate}&to=${this.currentDate}`, '_blank');
      });
    }
  }

  async autoSchedule() {
    const text = document.getElementById('timeline-journal-input').value.trim();
    const date = this.currentDate;
    const bar = document.getElementById('timeline-visual-bar');
    const details = document.getElementById('timeline-details-table');

    bar.innerHTML = `<div style="text-align:center; color:#3b82f6; padding:15px;">Calculating non-overlapping schedule...</div>`;

    const token = sessionStorage.getItem('tempo_web_token') || '';
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    try {
      const resp = await fetch('/api/schedule', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          content: text,
          date: date,
          round_minutes: 15,
          start: '09:00',
          break_issue: 'LUNCH',
          break_minutes: 45
        })
      });

      if (!resp.ok) {
        const err = await resp.json();
        bar.innerHTML = `<div style="color:#ef4444; font-size:13px; padding:10px;">⚠️ ${err.error || 'Schedule calculation failed'}</div>`;
        return;
      }

      const data = await resp.json();
      this.renderVisualTimeline(data.items, data.total_hours);
    } catch (e) {
      bar.innerHTML = `<div style="color:#ef4444; font-size:13px; padding:10px;">⚠️ Network error: ${e.message}</div>`;
    }
  }

  renderVisualTimeline(items, totalHours) {
    const bar = document.getElementById('timeline-visual-bar');
    const details = document.getElementById('timeline-details-table');
    if (!items || items.length === 0) {
      bar.innerHTML = `<div style="color:#64748b; font-size:13px; text-align:center; padding:15px;">No items scheduled for this day.</div>`;
      details.innerHTML = '';
      return;
    }

    let blocksHtml = `<div style="display: flex; gap: 8px; width: 100%; min-width: 600px;">`;
    let tableRows = '';

    items.forEach((item, idx) => {
      const isBreak = String(item.issue).toUpperCase().includes('LUNCH') || String(item.issue).toUpperCase().includes('BREAK');
      const bg = isBreak ? '#475569' : '#2563eb';
      const flexGrow = Math.max(1, Math.round(item.hours * 4));

      blocksHtml += `
        <div style="flex: ${flexGrow}; background: ${bg}; border-radius: 6px; padding: 8px; min-height: 48px; color: #fff; display: flex; flex-direction: column; justify-content: space-between; font-size: 11px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.3);">
          <div style="font-weight: 700;">${item.start} - ${item.end}</div>
          <div style="text-overflow: ellipsis; white-space: nowrap; overflow: hidden;">${item.issue} (${item.hours}h)</div>
        </div>
      `;

      tableRows += `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
          <td style="padding: 6px 8px; font-family: monospace;">${item.start} - ${item.end}</td>
          <td style="padding: 6px 8px; font-weight: 600; color: #60a5fa;">${item.issue}</td>
          <td style="padding: 6px 8px;">${item.hours}h</td>
          <td style="padding: 6px 8px; color: #cbd5e1;">${item.description ? item.description.split('\n')[0] : ''}</td>
        </tr>
      `;
    });
    blocksHtml += `</div>`;

    bar.innerHTML = blocksHtml;
    details.innerHTML = `
      <div style="display: flex; justify-content: space-between; margin-top: 10px; margin-bottom: 8px;">
        <span style="font-weight:600; color:#f8fafc;">Total Scheduled: ${totalHours}h</span>
        <span>Snapping: 15-min increments</span>
      </div>
      <table style="width: 100%; text-align: left; border-collapse: collapse; margin-top: 4px;">
        <thead>
          <tr style="color: #64748b; font-size: 11px; border-bottom: 1px solid rgba(255,255,255,0.1);">
            <th style="padding: 4px 8px;">Slot</th>
            <th style="padding: 4px 8px;">Issue</th>
            <th style="padding: 4px 8px;">Duration</th>
            <th style="padding: 4px 8px;">Notes</th>
          </tr>
        </thead>
        <tbody>${tableRows}</tbody>
      </table>
    `;
  }
}
