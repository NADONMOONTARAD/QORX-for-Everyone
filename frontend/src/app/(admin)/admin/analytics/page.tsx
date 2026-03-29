"use client";

import { CircleUserRound, UserPlus, Fingerprint, MessageSquare, CheckCircle2, Clock } from "lucide-react";

export default function AnalyticsPage() {
  const tickets = [
    { id: "T-001", user: "john@example.com", subject: "Cannot run DCF on Shell Company", status: "open", time: "2h ago" },
    { id: "T-002", user: "sarah@acme.com", subject: "How to use the Portfolio page?", status: "open", time: "5h ago" },
    { id: "T-003", user: "mike.dev@startup.io", subject: "Requesting feature: Insider Trading logs", status: "resolved", time: "1d ago" },
    { id: "T-004", user: "jane@finance.com", subject: "Login redirect issue", status: "resolved", time: "2d ago" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">
            User Management & Support
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            ข้อมูลบัญชีผู้ใช้งานระบบและตารางให้ความช่วยเหลือ (Helpdesk)
          </p>
        </div>
      </div>

      {/* Internal User Metrics */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="bg-white dark:bg-[#111] p-6 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm transition-all hover:shadow-md">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Registered Users</h3>
            <CircleUserRound className="h-5 w-5 text-blue-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-gray-900 dark:text-white">1,249</span>
            <span className="text-sm font-medium text-gray-500">Accounts</span>
          </div>
        </div>

        <div className="bg-white dark:bg-[#111] p-6 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm transition-all hover:shadow-md">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">New Signups (This Week)</h3>
            <UserPlus className="h-5 w-5 text-indigo-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-gray-900 dark:text-white">42</span>
            <span className="text-sm font-medium text-indigo-600">Users</span>
          </div>
        </div>

        <div className="bg-white dark:bg-[#111] p-6 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm transition-all hover:shadow-md">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400">Active Sessions</h3>
            <Fingerprint className="h-5 w-5 text-green-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-gray-900 dark:text-white">124</span>
            <span className="text-sm font-medium text-green-600">Online Now</span>
          </div>
        </div>
      </div>

      {/* Helpdesk Area */}
      <h2 className="text-xl font-bold text-gray-900 dark:text-white pt-4">User Support Desk</h2>
      <div className="bg-white dark:bg-[#111] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden transition-all hover:shadow-md">
        <div className="px-6 py-5 border-b border-gray-200 dark:border-gray-800 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-blue-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Recent Tickets</h3>
          </div>
          <button className="text-sm bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400 px-3 py-1.5 rounded-md font-medium hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors">
            View All
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm whitespace-nowrap">
            <thead className="bg-[#f8f9fa] dark:bg-[#161616] text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-6 py-4 font-medium">Ticket ID</th>
                <th className="px-6 py-4 font-medium">User</th>
                <th className="px-6 py-4 font-medium">Subject</th>
                <th className="px-6 py-4 font-medium">Status</th>
                <th className="px-6 py-4 font-medium">Time</th>
                <th className="px-6 py-4 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-800/60 text-gray-700 dark:text-gray-300">
              {tickets.map((ticket) => (
                <tr key={ticket.id} className="hover:bg-gray-50 dark:hover:bg-[#161616] transition-colors duration-150">
                  <td className="px-6 py-4 font-medium text-gray-900 dark:text-gray-200">{ticket.id}</td>
                  <td className="px-6 py-4">{ticket.user}</td>
                  <td className="px-6 py-4 truncate max-w-xs">{ticket.subject}</td>
                  <td className="px-6 py-4">
                    {ticket.status === "resolved" ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Resolved
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-50 text-yellow-700 border border-yellow-200 dark:bg-yellow-500/10 dark:text-yellow-400 dark:border-yellow-500/20">
                        <Clock className="w-3.5 h-3.5" /> Open
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-gray-500">{ticket.time}</td>
                  <td className="px-6 py-4 text-right">
                    <button className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium transition-colors">
                      Reply
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
