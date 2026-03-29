"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import Image from "next/image";
import { useTheme } from "next-themes";
import { usePathname, useRouter } from "next/navigation";
import styles from "./UserProfileDropdown.module.css";
import Lottie from "lottie-react";
import Link from "next/link";
import { createClient } from "@/utils/supabase/client";
import { CircleUserRound, Shield, LogOut } from "lucide-react";

import editAnimation from "@/assets/lottie/icons8-edit.json";
import gmailAnimation from "@/assets/lottie/icons8-gmail-logo.json";
import facebookAnimation from "@/assets/lottie/icons8-facebook.json";
import chatAnimation from "@/assets/lottie/icons8-chat.json";
import deleteAnimation from "@/assets/lottie/icons8-delete.json";
import sunAnimation from "@/assets/lottie/sun.json";

type Profile = {
  full_name: string | null;
  avatar_url: string | null;
  plan: string;
};

export function UserProfileDropdown() {
  const { theme, setTheme } = useTheme();
  const pathname = usePathname();
  const router = useRouter();
  const isAdminPage = pathname?.startsWith("/admin");
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Real Supabase user state
  const [user, setUser] = useState<{ id: string; email: string | undefined; app_metadata: any; user_metadata: any } | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  // Check if current user is an admin (runs client-side)
  const adminEmails = (process.env.NEXT_PUBLIC_ADMIN_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim())
    .filter(Boolean);
  const isAdmin = !!user?.email && adminEmails.includes(user.email);

  // Editable display name
  const [isEditingName, setIsEditingName] = useState(false);
  const [tempName, setTempName] = useState("");

  // Danger Zone
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [deleteInput, setDeleteInput] = useState("");

  const editLottieRef = useRef<any>(null);
  const emailLottieRef = useRef<any>(null);
  const supportLottieRef = useRef<any>(null);
  const deleteLottieRef = useRef<any>(null);
  const themeLottieRef = useRef<any>(null);
  const [pendingTheme, setPendingTheme] = useState<string | null>(null);

  const supabase = createClient();

  // ─── Load user + profile on mount ───
  useEffect(() => {
    const loadUser = async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) { setLoading(false); return; }
      setUser({ 
        id: user.id, 
        email: user.email, 
        app_metadata: user.app_metadata,
        user_metadata: user.user_metadata
      });

      const { data: profileData } = await supabase
        .from("profiles")
        .select("full_name, avatar_url, plan")
        .eq("id", user.id)
        .single();

      const meta = user.user_metadata;
      if (profileData) {
        // Merge DB profile with metadata if fields are missing
        const mergedProfile = {
          ...profileData,
          avatar_url: profileData.avatar_url || meta?.avatar_url || meta?.picture || null,
          full_name: profileData.full_name || meta?.full_name || meta?.name || user.email || "ผู้ใช้งาน"
        };
        setProfile(mergedProfile);
        setTempName(mergedProfile.full_name);
      } else {
        // Fallback to auth metadata (Google fills this on first login)
        setProfile({
          full_name: meta?.full_name ?? meta?.name ?? user.email ?? null,
          avatar_url: meta?.avatar_url ?? meta?.picture ?? null,
          plan: "free",
        });
        setTempName(meta?.full_name ?? meta?.name ?? user.email ?? "");
      }
      setLoading(false);
    };
    loadUser();
  }, []);

  // ─── Sync theme icon on first render ───
  useEffect(() => {
    if (!themeLottieRef.current) return;
    const frame = theme === "dark" ? 14 : 0;
    themeLottieRef.current.goToAndStop(frame, true);
  }, []);

  const prevTheme = useRef(theme);
  useEffect(() => {
    if (prevTheme.current === theme) return;
    prevTheme.current = theme;
    if (themeLottieRef.current && !pendingTheme) {
      const frame = theme === "dark" ? 14 : 0;
      themeLottieRef.current.goToAndStop(frame, true);
    }
  }, [theme, pendingTheme]);

  const handleToggleTheme = () => {
    if (pendingTheme) return;
    if (theme === "dark") {
      setPendingTheme("light");
      themeLottieRef.current?.playSegments([14, 0], true);
    } else {
      setPendingTheme("dark");
      themeLottieRef.current?.playSegments([0, 14], true);
    }
  };

  const handleThemeAnimationComplete = () => {
    if (pendingTheme) {
      setTheme(pendingTheme);
      setPendingTheme(null);
    }
  };

  const handleMouseEnter = (ref: React.RefObject<any>) => {
    if (ref.current) ref.current.goToAndPlay(0, true);
  };
  const handleMouseLeave = (ref: React.RefObject<any>) => {
    if (ref.current) {
      ref.current.stop();
      const frames = ref.current.getDuration(true);
      ref.current.goToAndStop(frames > 0 ? frames - 1 : 24, true);
    }
  };
  const handleDOMLoaded = (ref: React.RefObject<any>) => {
    if (ref.current) {
      const frames = ref.current.getDuration(true);
      ref.current.goToAndStop(frames > 0 ? frames - 1 : 24, true);
    }
  };

  const toggleDropdown = () => {
    setIsOpen((prev) => !prev);
    if (isOpen) {
      setIsDeleteOpen(false);
      setDeleteInput("");
      setIsEditingName(false);
    }
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setIsDeleteOpen(false);
        setDeleteInput("");
        setIsEditingName(false);
      }
    };
    if (isOpen) document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  // ─── Save edited name to profiles table ───
  const handleSaveName = async () => {
    if (tempName.trim().length === 0) return;
    setIsEditingName(false);
    if (!user) return;
    
    // Get the current avatar to preserve it
    const currentAvatar = profile?.avatar_url || user?.user_metadata?.avatar_url || user?.user_metadata?.picture;
    
    setProfile((p) => (p ? { ...p, full_name: tempName.trim(), avatar_url: currentAvatar } : p));
    
    await supabase
      .from("profiles")
      .upsert({ 
        id: user.id, 
        full_name: tempName.trim(),
        avatar_url: currentAvatar
      });
  };

  const handleKeyDownName = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") handleSaveName();
    if (e.key === "Escape") {
      setTempName(profile?.full_name ?? "");
      setIsEditingName(false);
    }
  };

  // ─── Real logout ───
  const handleLogout = async () => {
    await supabase.auth.signOut()
    window.location.href = "/"
  };

  // ─── Delete account ───
  const handleDeleteAccount = async () => {
    if (deleteInput !== "DELETE" || !user) return;
    
    // 1. Delete user profile from our database
    const { error } = await supabase
      .from("profiles")
      .delete()
      .eq("id", user.id);
    
    if (error) {
      console.error("Error deleting profile:", error);
      alert("เกิดข้อผิดพลาดในการลบข้อมูลโปรไฟล์");
      return;
    }

    // 2. Sign out (The user record in auth.users remains, but profile is gone)
    await supabase.auth.signOut();
    setIsOpen(false);
    window.location.href = "/";
  };

  // Detect provider (google vs email/facebook)
  const providers: string[] = user?.app_metadata?.providers ?? []
  const providerName: string = user?.app_metadata?.provider ?? ""
  const isGoogle = providerName === "google" || providers.includes("google")
  const displayName = profile?.full_name ?? user?.email ?? "ผู้ใช้งาน";
  const avatarUrl = profile?.avatar_url;
  const planLabel = profile?.plan === "pro" ? "Pro Plan" : "Free Plan";
  const emailDisplay = user?.email ?? "";

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.avatarButton} style={{ opacity: 0.4, width: 36, height: 36 }} />
      </div>
    );
  }

  // Not logged in: show Login button
  if (!user) {
    return (
      <div className={styles.container}>
        <a href="/login" className={styles.avatarButton} title="Sign In" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <CircleUserRound className="text-gray-500 hover:scale-110 transition-transform" size={26} strokeWidth={1.5} />
        </a>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <button
        ref={triggerRef}
        className={`${styles.avatarButton} group`}
        onClick={toggleDropdown}
        data-open={isOpen}
        aria-label="User Profile"
        title="Settings & Profile"
      >
        {avatarUrl ? (
          <Image
            src={avatarUrl}
            alt="Profile"
            width={36}
            height={36}
            className={styles.avatarImage}
            style={{ borderRadius: "50%", objectFit: "cover" }}
            referrerPolicy="no-referrer"
          />
        ) : (
          <CircleUserRound size={26} strokeWidth={1.5} className="text-gray-500 transition-transform" />
        )}
      </button>

      {isOpen && (
        <div className={styles.dropdown} ref={dropdownRef}>
          {/* Header */}
          <div className={styles.profileHeader}>
            {avatarUrl ? (
              <Image
                src={avatarUrl}
                alt="Profile Large"
                width={64}
                height={64}
                className={styles.profileAvatarLarge}
                style={{ borderRadius: "50%", objectFit: "cover" }}
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className={`${styles.profileAvatarLarge} bg-gray-100 dark:bg-gray-800 flex items-center justify-center rounded-full`}>
                <CircleUserRound size={36} strokeWidth={1.5} className="text-gray-400" />
              </div>
            )}

            <div className={styles.nameContainer}>
              {isEditingName ? (
                <div className={styles.nameInputWrapper}>
                  <input
                    type="text"
                    value={tempName}
                    onChange={(e) => setTempName(e.target.value)}
                    onKeyDown={handleKeyDownName}
                    autoFocus
                    className={styles.nameInput}
                  />
                  <button onClick={handleSaveName} className={styles.nameInputBtn}>
                    Save
                  </button>
                </div>
              ) : (
                <>
                  <div
                    className={styles.nameContainer}
                    style={{ margin: 0, padding: 0 }}
                    onMouseEnter={() => handleMouseEnter(editLottieRef)}
                    onMouseLeave={() => handleMouseLeave(editLottieRef)}
                  >
                    <span
                      className={styles.displayName}
                      onClick={() => { setTempName(profile?.full_name ?? ""); setIsEditingName(true); }}
                      title="Click to edit name"
                    >
                      {displayName}
                    </span>
                    <span style={{ display: "inline-flex", width: 18, height: 18, marginLeft: 6 }} className={styles.iconWrapper}>
                      <Lottie
                        lottieRef={editLottieRef}
                        animationData={editAnimation}
                        loop={false}
                        autoplay={false}
                        style={{ width: "100%", height: "100%" }}
                        onDOMLoaded={() => handleDOMLoaded(editLottieRef)}
                      />
                    </span>
                  </div>
                  <span className={styles.displayBadge}>{planLabel}</span>
                </>
              )}
            </div>

            <div
              className={styles.emailRow}
              onMouseEnter={() => handleMouseEnter(emailLottieRef)}
              onMouseLeave={() => handleMouseLeave(emailLottieRef)}
            >
              <span className={styles.emailText}>{emailDisplay}</span>
              <span style={{ display: "inline-flex", width: 16, height: 16 }} className={styles.brandIconWrapper}>
                <Lottie
                  lottieRef={emailLottieRef}
                  animationData={isGoogle ? gmailAnimation : facebookAnimation}
                  loop={false}
                  autoplay={false}
                  style={{ width: "100%", height: "100%" }}
                  onDOMLoaded={() => handleDOMLoaded(emailLottieRef)}
                />
              </span>
            </div>
          </div>

          <div className={styles.menuList}>
            {/* Theme */}
            <button className={styles.menuItem} onClick={handleToggleTheme}>
              <span style={{ display: "inline-flex", width: 20, height: 20 }} className={styles.iconWrapper}>
                <Lottie
                  lottieRef={themeLottieRef}
                  animationData={sunAnimation}
                  loop={false}
                  autoplay={false}
                  style={{ width: "100%", height: "100%" }}
                  onComplete={handleThemeAnimationComplete}
                />
              </span>
              <span>สลับโหมดสว่าง / มืด</span>
            </button>

            {/* Support */}
            <a
              href="mailto:support@qorx.com?subject=รายงานปัญหา / เสนอแนะ"
              className={styles.menuItem}
              style={{ textDecoration: "none" }}
              onMouseEnter={() => handleMouseEnter(supportLottieRef)}
              onMouseLeave={() => handleMouseLeave(supportLottieRef)}
            >
              <span style={{ display: "inline-flex", width: 20, height: 20 }} className={styles.iconWrapper}>
                <Lottie
                  lottieRef={supportLottieRef}
                  animationData={chatAnimation}
                  loop={false}
                  autoplay={false}
                  style={{ width: "100%", height: "100%" }}
                  onDOMLoaded={() => handleDOMLoaded(supportLottieRef)}
                />
              </span>
              <span>ติดต่อสอบถาม / รายงานปัญหา</span>
            </a>

            {/* Admin Dashboard link – only visible to admins when NOT on admin pages */}
            {isAdmin && !isAdminPage && (
              <Link href="/admin" className={`${styles.menuItem} group`} style={{ textDecoration: "none" }}>
                <div className={styles.iconWrapper} style={{ width: 20, height: 20, display: "flex", alignItems: "center", filter: "none" }}>
                  <Shield size={18} style={{ color: "var(--text-secondary, #64748b)" }} className="group-hover:scale-110 transition-transform" />
                </div>
                <span>Admin Dashboard</span>
              </Link>
            )}


            <div className={styles.separator} />

            {/* Delete Account */}
            <button
              className={styles.menuItemManage}
              onClick={() => setIsDeleteOpen(!isDeleteOpen)}
              style={{ padding: "8px 14px" }}
              onMouseEnter={() => handleMouseEnter(deleteLottieRef)}
              onMouseLeave={() => handleMouseLeave(deleteLottieRef)}
            >
              <span style={{ display: "inline-flex", width: 20, height: 20 }} className={styles.iconWrapper}>
                <Lottie
                  lottieRef={deleteLottieRef}
                  animationData={deleteAnimation}
                  loop={false}
                  autoplay={false}
                  style={{ width: "100%", height: "100%" }}
                  onDOMLoaded={() => handleDOMLoaded(deleteLottieRef)}
                />
              </span>
              <span style={{ color: "var(--text-secondary, #64748b)" }}>ลบบัญชีผู้ใช้</span>
              <span className={`${styles.iconWrapperCaret} ${isDeleteOpen ? styles.open : ""}`}>▼</span>
            </button>

            <div className={`${styles.dangerZoneContainer} ${isDeleteOpen ? styles.open : ""}`}>
              <div className={styles.dangerZoneContent}>
                <span className={styles.dangerText}>
                  การลบไม่สามารถกู้คืนได้ พิมพ์ <b>DELETE</b> ด้านล่างเพื่อยืนยัน
                </span>
                <input
                  type="text"
                  placeholder="พิมพ์ DELETE"
                  value={deleteInput}
                  onChange={(e) => setDeleteInput(e.target.value)}
                  className={styles.deleteInput}
                />
                <button
                  className={`${styles.deleteButton} ${deleteInput === "DELETE" ? styles.enabled : ""}`}
                  onClick={handleDeleteAccount}
                  disabled={deleteInput !== "DELETE"}
                >
                  ลบบัญชีอย่างถาวร
                </button>
              </div>
            </div>

            <div className={styles.separator} />

            {/* Logout */}
            <button className={`${styles.menuItem} group`} onClick={handleLogout}>
              <div className={styles.iconWrapper} style={{ width: 22, height: 22, display: "flex", alignItems: "center", filter: "none" }}>
                <LogOut size={20} style={{ color: "#ef4444" }} className="group-hover:-translate-x-1 transition-transform" />
              </div>
              <span style={{ color: "#ef4444" }}>ออกจากระบบ</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
