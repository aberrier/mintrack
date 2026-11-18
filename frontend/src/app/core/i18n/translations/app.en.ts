export default {
  nav: {
    label: 'Main navigation',
    home: 'Home',
    profile: 'Profile',
  },
  errors: {
    unknown: 'Something went wrong, try again',
  },
  home: {
    title: 'MinTrack',
    status: {
      checking: 'Checking the server…',
      online: 'Online',
      degraded: 'Online, but the database is unavailable',
      offline: 'Cannot reach the server',
    },
  },
  login: {
    title: 'Log in',
    username: 'Username',
    password: 'Password',
    submit: 'Log in',
    errors: {
      wrong: 'Wrong username or password',
      rateLimited: 'Too many failed attempts, try again in a few minutes',
    },
  },
  password: {
    title: 'Set your password',
    loading: 'Checking the link…',
    invalid: 'This link is invalid or has expired. Ask your admin for a new one.',
    account: 'Account',
    password: 'New password',
    hint: '15 to 128 characters',
    submit: 'Set password and log in',
  },
  profile: {
    title: 'Profile',
    timezone: {
      label: 'Time zone',
      hint: 'Air times are shown in this time zone',
      saved: 'Time zone saved',
    },
    password: {
      title: 'Change password',
      current: 'Current password',
      new: 'New password',
      hint: '15 to 128 characters',
      submit: 'Change password',
      wrong: 'Wrong current password',
      changed: 'Password changed, your other devices were signed out',
    },
    users: 'Manage users',
    logout: 'Log out',
    logoutEverywhere: 'Log out everywhere',
  },
  adminUsers: {
    title: 'Users',
    create: {
      username: 'Username',
      hint: 'Letters, digits, dots, dashes and underscores',
      submit: 'Invite',
      taken: 'This username is taken',
    },
    link: {
      intro: 'Send this link to {username}. It is shown only once.',
      copy: 'Copy link',
      copied: 'Link copied',
    },
    status: {
      invited: 'Invited',
      invitation_expired: 'Invitation expired',
      active: 'Active',
      disabled: 'Disabled',
    },
    admin: 'Admin',
    lastSeen: 'Last seen {date}',
    newLink: 'New link',
    disable: 'Disable',
    enable: 'Enable',
    lastAdmin: 'The last active admin cannot be disabled',
  },
};
