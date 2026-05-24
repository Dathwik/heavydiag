# PDF/HTML diagnostic report generator
"""
report_generator.py
-------------------
Generates a styled HTML diagnostic report at the end of a session.

The report documents:
  - Session metadata (vehicle, date, technician)
  - All DTCs encountered (active and historical)
  - Guided diagnosis steps taken for each DTC
  - Resolution outcome

This directly demonstrates the "technical documentation" skill that
PACCAR calls out in the job description.
"""

import os
import time
from typing import Optional


class ReportGenerator:
    """Generates HTML diagnostic session reports."""

    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports_out")

    def generate(self, dtc_history: list, vehicle_info: Optional[dict] = None) -> str:
        """
        Generate an HTML report and save to OUTPUT_DIR.
        Returns the file path.
        """
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename  = f"diagnostic_report_{timestamp}.html"
        filepath  = os.path.join(self.OUTPUT_DIR, filename)

        vehicle = vehicle_info or {
            "make_model": "Kenworth T680",
            "vin":        "1XKWDB0X0KJ123456",
            "engine":     "PACCAR MX-13",
            "mileage":    "248,315 mi",
            "technician": "HeavyDiag Simulator",
        }

        html = self._build_html(dtc_history, vehicle, timestamp)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        return filepath

    def _build_html(self, dtcs: list, vehicle: dict, timestamp: str) -> str:
        date_str = time.strftime("%B %d, %Y at %I:%M %p")
        dtc_rows = self._build_dtc_rows(dtcs)
        dtc_count = len(dtcs)
        resolved  = sum(1 for d in dtcs if d.resolution == "resolved")
        escalated = sum(1 for d in dtcs if d.resolution == "escalate")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HeavyDiag Diagnostic Report — {date_str}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Segoe UI", Arial, sans-serif;
    background: #F4F6F9;
    color: #1A2332;
    font-size: 14px;
    line-height: 1.5;
  }}
  .header {{
    background: #003087;
    color: white;
    padding: 28px 40px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .header h1 {{
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 1px;
  }}
  .header .subtitle {{
    font-size: 12px;
    opacity: 0.8;
    margin-top: 4px;
  }}
  .header .date {{
    font-size: 13px;
    opacity: 0.9;
    text-align: right;
  }}
  .container {{ max-width: 960px; margin: 32px auto; padding: 0 24px; }}
  .section {{
    background: white;
    border-radius: 8px;
    border: 1px solid #DDE2EA;
    margin-bottom: 24px;
    overflow: hidden;
  }}
  .section-header {{
    background: #F8F9FB;
    border-bottom: 1px solid #DDE2EA;
    padding: 14px 20px;
    font-size: 12px;
    font-weight: 700;
    color: #5A6A7E;
    text-transform: uppercase;
    letter-spacing: 0.8px;
  }}
  .section-body {{ padding: 20px; }}
  .vehicle-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
  }}
  .vehicle-field label {{
    font-size: 11px;
    color: #8A9BB0;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    display: block;
    margin-bottom: 4px;
  }}
  .vehicle-field span {{
    font-size: 14px;
    font-weight: 600;
    color: #1A2332;
  }}
  .summary-cards {{
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
  }}
  .summary-card {{
    flex: 1;
    background: white;
    border-radius: 8px;
    border: 1px solid #DDE2EA;
    padding: 16px 20px;
    text-align: center;
  }}
  .summary-card .num {{
    font-size: 32px;
    font-weight: 800;
    line-height: 1;
    margin-bottom: 4px;
  }}
  .summary-card .label {{
    font-size: 11px;
    color: #8A9BB0;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .num-total   {{ color: #1A2332; }}
  .num-resolved {{ color: #22C55E; }}
  .num-escalated {{ color: #F59E0B; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  th {{
    background: #F8F9FB;
    color: #5A6A7E;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 10px 12px;
    text-align: left;
    border-bottom: 2px solid #DDE2EA;
  }}
  td {{
    padding: 12px 12px;
    border-bottom: 1px solid #F0F2F5;
    vertical-align: top;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #F8FAFC; }}
  .badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
  }}
  .badge-critical {{ background: #FEE2E2; color: #DC2626; }}
  .badge-warning  {{ background: #FEF3C7; color: #D97706; }}
  .badge-info     {{ background: #DBEAFE; color: #2563EB; }}
  .badge-resolved {{ background: #DCFCE7; color: #16A34A; }}
  .badge-escalate {{ background: #FEF9C3; color: #CA8A04; }}
  .badge-open     {{ background: #F3F4F6; color: #6B7280; }}
  .dtc-code {{
    font-family: "Consolas", monospace;
    font-weight: 700;
    font-size: 13px;
    color: #1A2332;
  }}
  .steps-list {{
    list-style: none;
    margin-top: 6px;
    font-size: 12px;
    color: #5A6A7E;
  }}
  .steps-list li {{
    padding: 2px 0;
    padding-left: 14px;
    position: relative;
  }}
  .steps-list li::before {{
    content: "›";
    position: absolute;
    left: 0;
    color: #0088FF;
  }}
  .footer {{
    text-align: center;
    color: #8A9BB0;
    font-size: 12px;
    padding: 24px 0;
  }}
  .no-dtcs {{
    text-align: center;
    color: #8A9BB0;
    padding: 40px;
    font-size: 15px;
  }}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>⬡ HEAVYDIAG — DIAGNOSTIC REPORT</h1>
    <div class="subtitle">Off-Board Diagnostic Platform  |  SAE J1939 CAN Bus Diagnostics</div>
  </div>
  <div class="date">
    Generated: {date_str}<br>
    Session ID: {timestamp}
  </div>
</div>

<div class="container">

  <!-- Summary Cards -->
  <div class="summary-cards">
    <div class="summary-card">
      <div class="num num-total">{dtc_count}</div>
      <div class="label">DTCs Encountered</div>
    </div>
    <div class="summary-card">
      <div class="num num-resolved">{resolved}</div>
      <div class="label">Resolved</div>
    </div>
    <div class="summary-card">
      <div class="num num-escalated">{escalated}</div>
      <div class="label">Escalated</div>
    </div>
    <div class="summary-card">
      <div class="num" style="color:#3B82F6">{dtc_count - resolved - escalated}</div>
      <div class="label">Open / In Progress</div>
    </div>
  </div>

  <!-- Vehicle Info -->
  <div class="section">
    <div class="section-header">Vehicle Information</div>
    <div class="section-body">
      <div class="vehicle-grid">
        <div class="vehicle-field">
          <label>Make / Model</label>
          <span>{vehicle["make_model"]}</span>
        </div>
        <div class="vehicle-field">
          <label>VIN</label>
          <span>{vehicle["vin"]}</span>
        </div>
        <div class="vehicle-field">
          <label>Engine</label>
          <span>{vehicle["engine"]}</span>
        </div>
        <div class="vehicle-field">
          <label>Mileage</label>
          <span>{vehicle["mileage"]}</span>
        </div>
        <div class="vehicle-field">
          <label>Technician</label>
          <span>{vehicle["technician"]}</span>
        </div>
        <div class="vehicle-field">
          <label>Protocol</label>
          <span>SAE J1939 / CAN 2.0B (29-bit)</span>
        </div>
      </div>
    </div>
  </div>

  <!-- DTC Table -->
  <div class="section">
    <div class="section-header">Diagnostic Trouble Codes — Session Log</div>
    <div class="section-body" style="padding: 0;">
      {dtc_rows if dtc_rows else '<div class="no-dtcs">✅ No DTCs recorded in this session.</div>'}
    </div>
  </div>

  <div class="footer">
    HeavyDiag v1.0 — Off-Board Diagnostic Platform<br>
    Built with Python · PyQt5 · SAE J1939 · Agile Development<br>
    <em>Portfolio project demonstrating PACCAR Diagnostic Software Engineer competencies</em>
  </div>

</div>
</body>
</html>"""

    def _build_dtc_rows(self, dtcs: list) -> str:
        if not dtcs:
            return ""

        rows = []
        rows.append("""
        <table>
          <thead>
            <tr>
              <th>DTC Code</th>
              <th>Component</th>
              <th>Severity</th>
              <th>FMI Cause</th>
              <th>OC</th>
              <th>Resolution</th>
              <th>Diagnosis Steps</th>
            </tr>
          </thead>
          <tbody>
        """)

        for dtc in dtcs:
            sev_class = {
                "critical": "badge-critical",
                "warning":  "badge-warning",
                "info":     "badge-info",
            }.get(dtc.severity.value, "badge-info")

            res_class = {
                "resolved": "badge-resolved",
                "escalate": "badge-escalate",
                "cleared":  "badge-info",
            }.get(dtc.resolution, "badge-open")
            res_text = dtc.resolution.upper() if dtc.resolution else "OPEN"

            steps_html = ""
            if dtc.diagnosis_log:
                steps_html = "<ul class='steps-list'>"
                for step in dtc.diagnosis_log[:8]:
                    steps_html += f"<li>{step}</li>"
                if len(dtc.diagnosis_log) > 8:
                    steps_html += f"<li>… {len(dtc.diagnosis_log) - 8} more steps</li>"
                steps_html += "</ul>"
            else:
                steps_html = "<span style='color:#C0C8D4;font-size:12px;'>No guided diagnosis performed</span>"

            rows.append(f"""
            <tr>
              <td><span class="dtc-code">{dtc.dtc_code}</span></td>
              <td>{dtc.component_name}<br>
                  <span style="font-size:11px;color:#8A9BB0;">{dtc.subsystem}</span></td>
              <td><span class="badge {sev_class}">{dtc.severity.value.upper()}</span></td>
              <td style="font-size:12px;">{dtc.fmi_cause}</td>
              <td style="text-align:center;">{dtc.occurrence_count}</td>
              <td><span class="badge {res_class}">{res_text}</span></td>
              <td>{steps_html}</td>
            </tr>
            """)

        rows.append("</tbody></table>")
        return "".join(rows)