export const navigation = [
  { path: '/', label: 'Dashboard', permissions: ['attendance.read.self'] },
  { path: '/leave', label: 'Leave', permissions: ['leave.read.self'] },
  {
    path: '/team',
    label: 'Team',
    permissions: ['employee.read.team', 'employee.read.any'],
  },
  { path: '/profile', label: 'Profile', permissions: ['profile.read.self'] },
  {
    path: '/admin/employees',
    label: 'Employees',
    permissions: ['employee.read.any'],
  },
  { path: '/admin/teams', label: 'Teams', permissions: ['team.manage.any'] },
  {
    path: '/admin/locations',
    label: 'Work locations',
    permissions: ['location.manage.any'],
  },
  {
    path: '/admin/reports',
    label: 'Reports',
    permissions: ['report.export.any'],
  },
  {
    path: '/admin/all-attendance',
    label: 'All attendance',
    permissions: ['attendance.read.any'],
  },
] as const
