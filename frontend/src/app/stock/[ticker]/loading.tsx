import skeletonStyles from "../../(admin)/admin/portfolio/skeleton.module.css";
import styles from "./stock.module.css";

export default function StockLoading() {
  return (
    <div className={styles.page}>
      {/* Back link skeleton */}
      <div
        className={skeletonStyles.skeletonText}
        style={{ width: 100, marginBottom: 8 }}
      />

      {/* Header skeleton */}
      <header className={styles.header} style={{ marginBottom: 0 }}>
        <div className={styles.headerTopRow}>
          <div
            className={skeletonStyles.skeletonTextXl}
            style={{ width: 320 }}
          />
          <div
            className={skeletonStyles.skeleton}
            style={{ width: 140, height: 28, borderRadius: 999 }}
          />
        </div>
        <div
          className={skeletonStyles.skeletonText}
          style={{ width: 200, marginTop: 6 }}
        />
      </header>

      {/* Metric cards skeleton */}
      <section className={styles.metricPanel}>
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className={styles.metricCardModern}
            style={{ minHeight: 130 }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div
                className={skeletonStyles.skeleton}
                style={{ width: 24, height: 24, borderRadius: 6 }}
              />
              <div
                className={skeletonStyles.skeletonText}
                style={{ width: 100 }}
              />
            </div>
            <div
              className={skeletonStyles.skeletonTextXl}
              style={{ width: "70%", marginTop: 10 }}
            />
            <div
              className={skeletonStyles.skeletonText}
              style={{ width: "50%", marginTop: 6 }}
            />
          </div>
        ))}
      </section>

      {/* Quality Overview skeleton */}
      <section className={styles.qualityPanel}>
        <div className={styles.qualityPanelHeader}>
          <div
            className={skeletonStyles.skeletonTextLg}
            style={{ width: 180 }}
          />
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: 18,
          }}
        >
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className={skeletonStyles.skeletonCard}
              style={{ height: 180, borderRadius: 20 }}
            />
          ))}
        </div>
      </section>

      {/* Revenue Breakdown skeleton */}
      <section
        className={skeletonStyles.skeletonCard}
        style={{ height: 320, borderRadius: 20 }}
      />

      {/* Valuation section skeleton */}
      <section
        className={skeletonStyles.skeletonCard}
        style={{ height: 280, borderRadius: 20 }}
      />
    </div>
  );
}
