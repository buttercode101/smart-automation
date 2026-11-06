import { host, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

function Chain({ chain }) {
  return jsxs('div', {
    className: 'flex flex-col gap-1 p-2 text-sm',
    children: [
      jsx('div', { className: 'font-medium', children: chain.chain_id }),
      jsx('div', {
        className: 'text-(--ui-text-tertiary)',
        children: `${chain.nodes.length} steps · ${chain.edges.length} dependencies`
      }),
      ...chain.nodes.map((n) =>
        jsx('div', {
          key: n.id,
          className: 'flex items-center gap-2',
          children: [
            jsx('span', {
              className: n.status === 'succeeded' ? 'text-green-500' : n.status === 'ready' ? 'text-yellow-500' : 'text-(--ui-text-tertiary)',
              children: n.status === 'succeeded' ? '●' : n.status === 'ready' ? '◐' : '○'
            }),
            jsx('span', { children: n.id }),
            jsx('span', { className: 'text-(--ui-text-tertiary) text-xs', children: n.status })
          ]
        })
      ),
      jsx('div', {
        className: 'text-xs text-(--ui-text-tertiary)',
        children: 'Manual chain-runner: advance via orchestrator_trigger_chain in chat (approvals enforced).'
      })
    ]
  })
}

function TimelinePane() {
  const [data, setData] = useValue(host.state.gateway)
  return jsxs('div', {
    className: 'flex h-full flex-col gap-2 p-3 overflow-auto',
    children: [
      jsx('div', { className: 'font-medium', children: 'Smart Automation Timeline' }),
      jsx('div', {
        className: 'text-xs text-(--ui-text-tertiary)',
        children: 'Read-only view. Mutations go through agent tools so approvals fire.'
      }),
      jsx('div', {
        className: 'text-xs',
        children: 'Open a chain in chat with orchestrator_graph, then view it here.'
      })
    ]
  })
}

export default {
  id: 'smart-automation',
  name: 'Smart Automation',
  register(ctx) {
    ctx.register({
      id: 'pane',
      area: 'panes',
      title: 'smart automation',
      data: { placement: 'right', width: '320px' },
      render: () => jsx(TimelinePane, {})
    })
    ctx.register({
      id: 'chip',
      area: 'statusBar.right',
      order: 130,
      render: () =>
        jsx('button', {
          type: 'button',
          className: 'px-1.5 text-[0.6875rem] text-(--ui-text-tertiary)',
          onClick: () => host.notify({ kind: 'info', message: 'Smart Automation: no blocked chains' }),
          children: '🔗 auto'
        })
    })
  }
}
