"use client";

import { Activity, Database, ServerCrash, Clock, Box } from "lucide-react";

export default function AdminOverviewPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">
            System Overview
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            สถานะภาพรวมของเซิร์ฟเวอร์และฐานข้อมูลภายในระบบ
          </p>
        </div>
      </div>

      {/* Internal System Metric Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="bg-white dark:bg-[#111] p-6 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm transition-all hover:shadow-md">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Stocks in DB</h3>
            <Database className="h-5 w-5 text-blue-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-gray-900 dark:text-white">8,432</span>
            <span className="text-sm font-medium text-gray-500">Tickers</span>
          </div>
        </div>

        <div className="bg-white dark:bg-[#111] p-6 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm transition-all hover:shadow-md">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Cached API Responses</h3>
            <Box className="h-5 w-5 text-indigo-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-gray-900 dark:text-white">12.4k</span>
            <span className="text-sm font-medium text-gray-500">Rows</span>
          </div>
        </div>

        <div className="bg-white dark:bg-[#111] p-6 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm transition-all hover:shadow-md">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Tasks Pending (Queue)</h3>
            <Clock className="h-5 w-5 text-yellow-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-gray-900 dark:text-white">42</span>
            <span className="text-sm font-medium text-yellow-600">Pending</span>
          </div>
        </div>

        <div className="bg-white dark:bg-[#111] p-6 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm transition-all hover:shadow-md">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Server Status</h3>
            <Activity className="h-5 w-5 text-green-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-green-600 dark:text-green-500">Online</span>
            <span className="text-sm font-medium text-gray-500">99.9% Uptime</span>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-[#111] p-6 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm">
        <div className="flex items-center gap-3 text-gray-600 dark:text-gray-400">
          <ServerCrash className="w-5 h-5 text-gray-400 flex-shrink-0" />
          <p className="text-sm">
            Note: For detailed financial metrics (MRR, Churn) and advanced web analytics (Traffic, CAC, CTR), please refer to your <a href="https://dashboard.stripe.com" target="_blank" className="text-blue-600 dark:text-blue-400 hover:underline">Stripe Dashboard</a> and external analytics tools. This admin portal is dedicated strictly to internal system health and user support.
          </p>
        </div>
      </div>
    </div>
  );
}
