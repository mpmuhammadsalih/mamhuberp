"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import type { Order } from "@/lib/types";

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Order[]>("/api/orders").then(setOrders).catch((err) => setError(err.message));
  }, []);

  return (
    <AppShell>
      <div className="p-6">
        <h1 className="mb-4 text-2xl font-semibold">Orders</h1>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="crm-paper overflow-auto rounded-2xl shadow-sm">
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3">Order</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Payment</th>
                <th className="px-4 py-3">Website</th>
                <th className="px-4 py-3">Total</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.order_id} className="border-t border-[var(--line)]">
                  <td className="px-4 py-3 font-medium">{order.order_number}</td>
                  <td className="px-4 py-3">{new Date(order.order_date).toLocaleString()}</td>
                  <td className="px-4 py-3">{order.order_status}</td>
                  <td className="px-4 py-3">{order.payment_method}</td>
                  <td className="px-4 py-3">
                    {order.mh_order_id || order.erp_post_status === "ORDERED"
                      ? "Same as web"
                      : order.erp_post_status === "FAILED"
                        ? "Failed"
                        : order.erp_bill_no
                          ? `Bill ${order.erp_bill_no}`
                          : "—"}
                  </td>
                  <td className="px-4 py-3">QAR {order.total_amount.toFixed(2)}</td>
                  <td className="px-4 py-3">
                    {!order.erp_bill_no && order.order_status !== "Cancelled" && (
                      <button
                        type="button"
                        className="btn-ghost"
                        onClick={() => {
                          if (!window.confirm(`Remove ${order.order_number}? Only allowed before a sales invoice is created.`)) return;
                          api<Order>(`/api/orders/${order.order_id}/remove`, { method: "POST" })
                            .then((updated) => setOrders((prev) => prev.map((row) => (row.order_id === updated.order_id ? updated : row))))
                            .catch((err) => setError(err instanceof Error ? err.message : "Could not remove order"));
                        }}
                      >
                        Remove
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!orders.length && <p className="crm-paper-muted p-6 text-sm">No WhatsApp orders yet.</p>}
        </div>
      </div>
    </AppShell>
  );
}
