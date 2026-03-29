import Link from "next/link";
import styles from "./stock.module.css";
import Image from "next/image";

type BackLinkProps = {
  href: string;
};

export function BackLink({ href }: BackLinkProps) {
  return (
    <Link
      href={href}
      className={styles.backLink}
      title="Back to home"
    >
      <Image 
        src="/QORX.png" 
        alt="QORX" 
        width={180} 
        height={48} 
        style={{ objectFit: 'contain', width: 'auto', height: '48px', filter: 'var(--icon-filter, none)' }} 
        priority
      />
    </Link>
  );
}

