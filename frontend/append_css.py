
css_path = 'frontend/src/app/stock/[ticker]/stock.module.css'
styles = """

.cardTitleGroup {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.toggleGroup {
  display: flex;
  background: #f1f5f9;
  border-radius: 8px;
  padding: 4px;
  gap: 4px;
}

.toggleButton {
  border: none;
  background: transparent;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toggleButton:hover {
  color: #0f172a;
}

.toggleButton.active {
  background: #ffffff;
  color: #0f4dbc;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
"""

with open(css_path, 'a') as f:
    f.write(styles)
print("CSS appended.")
