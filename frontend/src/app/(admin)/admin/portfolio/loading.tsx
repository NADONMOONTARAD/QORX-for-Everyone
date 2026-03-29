import skeletonStyles from "./skeleton.module.css";
import styles from "./portfolio/portfolio.module.css";

export default function DashboardLoading() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <div className={skeletonStyles.skeletonTextXl} style={{ width: 200 }} />
          <div className={skeletonStyles.skeletonText} style={{ width: 320, marginTop: 8 }} />
        </div>
        <div className={styles.actionRow}>
          <div className={skeletonStyles.skeleton} style={{ width: 180, height: 42, borderRadius: 20 }} />
          <div className={skeletonStyles.skeleton} style={{ width: 90, height: 42, borderRadius: 999 }} />
          <div className={skeletonStyles.skeleton} style={{ width: 90, height: 42, borderRadius: 999 }} />
        </div>
      </header>

      <section className={styles.contentGrid}>
        <article className={`${styles.card} ${styles.portfolioCard}`}>
          <div className={styles.donutWrapper}>
            <div className={skeletonStyles.skeletonCircle} style={{ width: 180, height: 180 }} />
          </div>
          <div style={{ display: 'grid', gap: 14 }}>
            <div className={skeletonStyles.skeletonText} style={{ width: '80%' }} />
            <div className={skeletonStyles.skeletonText} style={{ width: '60%' }} />
            <div className={skeletonStyles.skeletonText} style={{ width: '50%' }} />
          </div>
        </article>

        <article className={styles.card}>
          <div className={skeletonStyles.skeletonTextLg} style={{ width: 120 }} />
          <div style={{ display: 'grid', gap: 18, marginTop: 20 }}>
            {[1, 2, 3, 4].map((i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between' }}>
                <div className={skeletonStyles.skeletonText} style={{ width: 100 }} />
                <div className={skeletonStyles.skeletonText} style={{ width: 60 }} />
              </div>
            ))}
          </div>
        </article>
      </section>

      <div className={skeletonStyles.skeletonCard} style={{ height: 300, borderRadius: 20 }} />

      <section className={styles.contentGrid}>
        <div className={skeletonStyles.skeletonCard} style={{ height: 260, borderRadius: 20 }} />

        <article className={styles.tableCard}>
          <div className={skeletonStyles.skeletonTextLg} style={{ width: 160 }} />
          <div className={skeletonStyles.skeletonText} style={{ width: 240, marginTop: 4 }} />
          <div style={{ marginTop: 16 }}>
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className={skeletonStyles.skeletonTableRow}>
                <div className={skeletonStyles.skeletonTableCell} style={{ maxWidth: 60 }} />
                <div className={skeletonStyles.skeletonTableCell} />
                <div className={skeletonStyles.skeletonTableCell} />
                <div className={skeletonStyles.skeletonTableCell} />
                <div className={skeletonStyles.skeletonTableCell} />
                <div className={skeletonStyles.skeletonTableCell} style={{ maxWidth: 70 }} />
              </div>
            ))}
          </div>
        </article>
      </section>
    </div>
  );
}
