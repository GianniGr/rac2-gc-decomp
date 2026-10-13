#include "include_asm.h"
extern int D_L00_001B0138 __attribute__((sda));
extern int D_L00_002472C0[][4];
extern void func_0031E528(void *);
extern void func_002FEE50(int);
extern void func_0029F338(void *);

void func_0031E6E8(char *object)
{
    char *data = *(char **)(object + 0x68);
    int index = *(int *)(data + 0x14);
    --D_L00_001B0138;
    D_L00_002472C0[index][0] = 0;
    func_0031E528(object);
    func_002FEE50(*(int *)(data + 0x44));
    func_0029F338(object);
}
