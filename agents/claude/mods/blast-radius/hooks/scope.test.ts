import { expect, test } from 'claude-code/testing'

// @ts-expect-error plain JavaScript module
import { hasShellSyntax, isBelow, isWithin, parseScope, staysInside } from './scope.mjs'

const rm = { kind: 'rm' }
const gitReset = { kind: 'git-reset' }
const ROOTS = ['/work/app', '/work/app-wt', '/Users/me/.claude-worktrees/app/feature']

test('a path is inside a root only when it really is under it', () => {
  expect(isWithin('/work/app', '/work/app')).toBe(true)
  expect(isBelow('/work/app', '/work/app')).toBe(false)
  expect(isBelow('/work/app/src/a.ts', '/work/app')).toBe(true)
  // a sibling that only shares the name prefix is not inside
  expect(isWithin('/work/app-other/x', '/work/app')).toBe(false)
  expect(isWithin('/work/app/../etc', '/work/appx')).toBe(false)
})

test('rm inside the project or a worktree runs without a question', () => {
  expect(staysInside(rm, ROOTS, ['/work/app/build', '/work/app/dist/x.js'])).toBe(true)
  expect(staysInside(rm, ROOTS, ['/work/app-wt/node_modules'])).toBe(true)
  expect(staysInside(rm, ROOTS, ['/Users/me/.claude-worktrees/app/feature/out'])).toBe(true)
})

test('rm that reaches outside, or removes a root itself, is held', () => {
  expect(staysInside(rm, ROOTS, ['/work/app/build', '/Users/me/Documents'])).toBe(false)
  expect(staysInside(rm, ROOTS, ['/work/app'])).toBe(false)
  expect(staysInside(rm, ROOTS, ['/work/app-wt'])).toBe(false)
  expect(staysInside(rm, ROOTS, ['/'])).toBe(false)
})

test('rm of paths that do not exist does nothing, so it is not held', () => {
  expect(staysInside(rm, ROOTS, [])).toBe(true)
})

test('git working-tree commands: the folder they run in decides', () => {
  expect(staysInside(gitReset, ROOTS, ['/work/app'])).toBe(true)
  expect(staysInside(gitReset, ROOTS, ['/work/app/packages/x'])).toBe(true)
  expect(staysInside(gitReset, ROOTS, ['/work/app-wt'])).toBe(true)
  expect(staysInside(gitReset, ROOTS, ['/Users/me/other-repo'])).toBe(false)
  expect(staysInside(gitReset, ROOTS, [])).toBe(false)
})

test('no roots, or an answer that cannot be read, means hold', () => {
  expect(staysInside(rm, [], ['/work/app/build'])).toBe(false)
  expect(parseScope('')).toEqual({ roots: [], paths: [] })
  expect(parseScope('/work/app\n')).toEqual({ roots: [], paths: [] })
})

test('scope.sh output is read into roots and paths', () => {
  const out = '/work/app\n/work/app-wt\n---\n/work/app/build\n'

  expect(parseScope(out)).toEqual({
    roots: ['/work/app', '/work/app-wt'],
    paths: ['/work/app/build'],
  })
  expect(parseScope('/\n/work/app\n---\n').roots).toEqual(['/work/app'])
})

test('words the code cannot resolve are held', () => {
  for (const w of ['$HOME/x', '"$DIR"/x', '$(pwd)/..', '`pwd`', '{a,b}', '~root/x']) {
    expect(hasShellSyntax(w)).toBe(true)
  }
  for (const w of ['build', './dist', '../x', '~', '~/x', '/tmp/a b', 'src/*.o']) {
    expect(hasShellSyntax(w)).toBe(false)
  }
})
