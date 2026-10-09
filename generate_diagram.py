"""
Generates high-resolution system architecture diagram docs/architecture.png
with a crisp, clean light-mode palette (green and white base).
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path

def generate_architecture_diagram():
    fig, ax = plt.subplots(figsize=(16, 9), dpi=300)
    fig.patch.set_facecolor('#F8FAFC')
    ax.set_facecolor('#F8FAFC')

    # Clean, crisp light-mode palette
    border_color = '#CBD5E1'
    box_bg = '#FFFFFF'
    text_color = '#0F172A'
    sub_color = '#475569'
    accent_green = '#047857'
    accent_blue = '#1E40AF'
    accent_amber = '#B45309'
    accent_red = '#B91C1C'
    accent_indigo = '#4338CA'

    # Title & Subtitle
    ax.text(0.5, 0.95, "S&P Global & CRISIL Tactical Stock Index Rebalancer (Module A)",
            color='#0F172A', fontsize=18, fontweight='bold', ha='center', va='center')
    ax.text(0.5, 0.915, "End-to-End System Architecture & Real-Time Quantitative Data Flow",
            color='#64748B', fontsize=11, ha='center', va='center')

    # Helper function to draw clean cards
    def draw_card(x, y, w, h, title, subtitle, items, border_c=border_color, header_c=accent_green):
        # Background card with subtle drop shadow appearance
        shadow = patches.FancyBboxPatch((x + 0.003, y - 0.003), w, h, boxstyle="round,pad=0.01,rounding_size=0.015",
                                        linewidth=0, facecolor='#E2E8F0', alpha=0.5)
        ax.add_patch(shadow)

        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.015",
                                      linewidth=1.2, edgecolor=border_c, facecolor=box_bg)
        ax.add_patch(rect)
        
        # Header banner line
        ax.plot([x, x + w], [y + h - 0.045, y + h - 0.045], color='#F1F5F9', lw=1.2)
        
        # Header text
        ax.text(x + 0.015, y + h - 0.025, title, color='#0F172A', fontsize=11, fontweight='bold', va='center')
        ax.text(x + w - 0.015, y + h - 0.025, subtitle, color=header_c, fontsize=9, fontweight='semibold', ha='right', va='center')
        
        # Content bullets
        y_pos = y + h - 0.075
        for item in items:
            ax.text(x + 0.02, y_pos, f"• {item}", color=sub_color, fontsize=9.5, va='center')
            y_pos -= 0.038

    # 1. Ingestion Layer
    draw_card(
        0.05, 0.50, 0.25, 0.35,
        "1. Multi-Source Ingestion", "INGESTION LAYER",
        [
            "Financial News Feeds (ET RSS)",
            "Corporate Filings (NSE RSS)",
            "Social Media Streams (Apify)",
            "Credibility Weights (1.0 / 0.8 / 0.3)",
            "SHA-256 Text Deduplication",
            "Pydantic RawTextItem Schema"
        ],
        border_c='#3B82F6', header_c=accent_blue
    )

    # 2. 7-Day Memory & RAG Layer
    draw_card(
        0.05, 0.08, 0.25, 0.35,
        "2. 7-Day Memory & RAG", "VECTOR ENGINE",
        [
            "Rolling 7-Day Storage Window",
            "Sentence-Transformers (384-dim)",
            "NumPy Feature Hash Fallback",
            "Cosine Similarity Evidence Search",
            "Exponential Recency Decay: e^(-λΔt)",
            "Automatic 7-Day Retention Purge"
        ],
        border_c='#059669', header_c=accent_green
    )

    # 3. AI/NLP Risk Engine
    draw_card(
        0.37, 0.50, 0.26, 0.35,
        "3. AI/NLP Risk Engine", "NLP PIPELINE",
        [
            "Nifty 10 Entity Alias Resolution",
            "Sentiment Polarity (-1.0 to +1.0)",
            "8-Class Financial Event Taxonomy",
            "Impact Severity Rubric (1 to 10)",
            "Source-Weighted Noise Attenuation",
            "NVIDIA Nemotron + Lexicon Mode"
        ],
        border_c='#D97706', header_c=accent_amber
    )

    # 4. Tactical Rebalancer (Module A)
    draw_card(
        0.37, 0.08, 0.26, 0.35,
        "4. Quantitative Rebalancer", "MODULE A CORE",
        [
            "Nifty 10 Basket (10% Benchmark)",
            "Exponential Tilting: w ∝ 0.10·exp(0.5·S)",
            "Bounds: 5% Min / 20% Max per stock",
            "Cycle Step Limit: Max ±2.0% Delta",
            "Max Turnover Limit: 10% per cycle",
            "Water-Filling Simplex Projection"
        ],
        border_c='#047857', header_c=accent_green
    )

    # 5. Interface & Monitoring Layer
    draw_card(
        0.70, 0.28, 0.25, 0.40,
        "5. Financial Dashboard", "DELIVERY LAYER",
        [
            "FastAPI Async REST Endpoints",
            "Real-Time Allocation Matrix & Bar",
            "Live NLP Signals Stream & Drawer",
            "Curated Replay Scenarios (A, B, C)",
            "Live Custom Headline Ingestion",
            "Green/White Institutional Terminal",
            "Full Legal & Methodology Modals"
        ],
        border_c='#4F46E5', header_c=accent_indigo
    )

    # Connective arrows
    arrow_props = dict(facecolor='#2563EB', edgecolor='#1D4ED8', width=2, headwidth=7, headlength=7)
    
    # Ingestion -> Memory
    ax.annotate('', xy=(0.175, 0.44), xytext=(0.175, 0.49),
                arrowprops=dict(facecolor='#059669', edgecolor='#047857', width=1.5, headwidth=6))
    
    # Ingestion -> Risk Engine
    ax.annotate('', xy=(0.36, 0.675), xytext=(0.31, 0.675), arrowprops=arrow_props)
    
    # Memory -> Risk Engine (Evidence grounding)
    ax.annotate('', xy=(0.36, 0.55), xytext=(0.31, 0.35),
                arrowprops=dict(facecolor='#059669', edgecolor='#047857', width=1.5, headwidth=6))
    
    # Risk Engine -> Rebalancer
    ax.annotate('', xy=(0.50, 0.44), xytext=(0.50, 0.49),
                arrowprops=dict(facecolor='#D97706', edgecolor='#B45309', width=1.5, headwidth=6))
    
    # Rebalancer -> Dashboard
    ax.annotate('', xy=(0.69, 0.45), xytext=(0.64, 0.28),
                arrowprops=dict(facecolor='#047857', edgecolor='#065F46', width=1.5, headwidth=6))

    # Risk Engine -> Dashboard (Signals feed)
    ax.annotate('', xy=(0.69, 0.55), xytext=(0.64, 0.675),
                arrowprops=dict(facecolor='#4F46E5', edgecolor='#4338CA', width=1.5, headwidth=6))

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    out_dir = Path("docs")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "architecture.png"
    plt.tight_layout()
    plt.savefig(out_file, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"Refreshed architecture diagram generated: {out_file}")

if __name__ == "__main__":
    generate_architecture_diagram()
