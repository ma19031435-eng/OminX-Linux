#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <wayland-client.h>
#include <wayland-server.h>
#include <xkbcommon/xkbcommon.h>
#include <xkbcommon/xkbcommon-keysyms.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>
static pid_t server_pid = -1;
static void cleanup(void) { if (server_pid > 1) { kill(server_pid, SIGKILL); waitpid(server_pid, NULL, 0); server_pid=-1; } }
static void require(int ok, const char *message) {
    if (!ok) { fprintf(stderr,"FAIL render runtime: %s (EGL=%x)\n",message,eglGetError()); exit(1); }
}
static void source_guest(void) {
    char line[256]; int valid=0; struct stat st;
    require(getuid()==1000 && geteuid()==1000, "unprivileged guest only");
    FILE *f=fopen("/proc/1/comm","r");
    require(f && fgets(line,sizeof line,f) && !strcmp(line,"init\n"),"source init identity"); fclose(f);
    require(!lstat("/etc/os-release",&st) && S_ISREG(st.st_mode) && st.st_uid==0 && !(st.st_mode&0022),"protected image identity");
    f=fopen("/etc/os-release","r"); require(f!=NULL,"image identity");
    while(fgets(line,sizeof line,f)) if(!strcmp(line,"ID=ominx\n")) valid=1;
    fclose(f); require(valid,"OminX source image");
    require(!lstat("/run/user/1000",&st) && S_ISDIR(st.st_mode) && st.st_uid==1000 && (st.st_mode&0777)==0700,"private runtime directory");
    setenv("XDG_RUNTIME_DIR","/run/user/1000",1);
}
static void protocol(void) {
    struct wl_display *server=wl_display_create(); char name[64];
    require(server!=NULL,"Wayland server creation");
    snprintf(name,sizeof name,"ominx-validation-%ld",(long)getpid());
    require(wl_display_add_socket(server,name)==0,"Wayland private listener");
    pid_t parent=getpid();
    server_pid=fork(); require(server_pid>=0,"Wayland fork");
    if(!server_pid) { if(prctl(PR_SET_PDEATHSIG,SIGKILL)||getppid()!=parent) _exit(1); wl_display_run(server); _exit(0); }
    struct wl_display *client=wl_display_connect(name);
    require(client && wl_display_roundtrip(client)>=0,"Wayland client/server sync");
    wl_display_disconnect(client); cleanup(); wl_display_destroy(server);
    puts("PASS Wayland shared-library protocol roundtrip");
}
static GLuint shader(GLenum type,const char *text) {
    GLuint value=glCreateShader(type); GLint ok=0;
    glShaderSource(value,1,&text,NULL); glCompileShader(value); glGetShaderiv(value,GL_COMPILE_STATUS,&ok);
    if(!ok) { char log[2048]; glGetShaderInfoLog(value,sizeof log,NULL,log); fprintf(stderr,"%s\n",log); }
    require(ok,"shader compilation"); return value;
}
int main(int argc,char **argv) {
    require(argc==2 && !strcmp(argv[1],"--guest-test"),"explicit guest invocation required");
    source_guest(); atexit(cleanup); alarm(30); protocol();
    struct xkb_context *x=xkb_context_new(XKB_CONTEXT_NO_FLAGS); require(x!=NULL,"XKB context");
    struct xkb_rule_names names={.rules="evdev",.model="pc105",.layout="us"};
    struct xkb_keymap *map=xkb_keymap_new_from_names(x,&names,XKB_KEYMAP_COMPILE_NO_FLAGS); require(map!=NULL,"source keyboard data");
    struct xkb_state *state=xkb_state_new(map); require(state!=NULL,"keyboard state");
    require(xkb_state_key_get_one_sym(state,38)==XKB_KEY_a,"US key mapping");
    xkb_state_update_key(state,50,XKB_KEY_DOWN);
    require(xkb_state_key_get_one_sym(state,38)==XKB_KEY_A,"shift key mapping");
    xkb_state_unref(state); xkb_keymap_unref(map); xkb_context_unref(x);
    puts("PASS XKB source keyboard data and modifiers");
    int card=open("/dev/dri/card0",O_RDWR|O_CLOEXEC); require(card>=0,"unprivileged DRM device access");
    drmVersionPtr version=drmGetVersion(card); require(version && version->name,"DRM driver query");
    printf("DRM driver: %.*s\n",version->name_len,version->name);
    drmModeRes *resources=drmModeGetResources(card);
    require(resources && resources->count_connectors>0 && resources->count_crtcs>0,"DRM display resources");
    drmModeFreeResources(resources); drmFreeVersion(version); close(card);
    puts("PASS DRM shared-library device/resource query");
    setenv("LIBGL_ALWAYS_SOFTWARE","1",1); setenv("GALLIUM_DRIVER","softpipe",1);
    PFNEGLGETPLATFORMDISPLAYEXTPROC get_display=(PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
    require(get_display!=NULL,"EGL platform extension");
    EGLDisplay d=get_display(EGL_PLATFORM_SURFACELESS_MESA,EGL_DEFAULT_DISPLAY,NULL);
    EGLint major,minor,count; EGLConfig config;
    require(d!=EGL_NO_DISPLAY && eglInitialize(d,&major,&minor),"source Mesa initialization");
    require(eglBindAPI(EGL_OPENGL_ES_API),"GLES API");
    const EGLint attrs[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES2_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_NONE};
    require(eglChooseConfig(d,attrs,&config,1,&count) && count==1,"EGL config");
    const EGLint context_attrs[]={EGL_CONTEXT_CLIENT_VERSION,2,EGL_NONE}, surface_attrs[]={EGL_WIDTH,32,EGL_HEIGHT,32,EGL_NONE};
    EGLContext c=eglCreateContext(d,config,EGL_NO_CONTEXT,context_attrs); EGLSurface surface=eglCreatePbufferSurface(d,config,surface_attrs);
    require(c!=EGL_NO_CONTEXT && surface!=EGL_NO_SURFACE && eglMakeCurrent(d,surface,surface,c),"EGL current context");
    const char *renderer=(const char*)glGetString(GL_RENDERER); require(renderer && strstr(renderer,"softpipe"),"software renderer identity");
    printf("Renderer: %s; GL: %s\n",renderer,glGetString(GL_VERSION));
    glViewport(0,0,32,32); glClearColor(1,0,0,1); glClear(GL_COLOR_BUFFER_BIT);
    unsigned char pixel[4]; glReadPixels(16,16,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
    require(pixel[0]>250 && pixel[1]<5 && pixel[2]<5,"rendered red framebuffer");
    GLuint vs=shader(GL_VERTEX_SHADER,"attribute vec2 p;void main(){gl_Position=vec4(p,0.0,1.0);}");
    GLuint fs=shader(GL_FRAGMENT_SHADER,"precision mediump float;void main(){gl_FragColor=vec4(0.0,1.0,0.0,1.0);}");
    GLuint program=glCreateProgram(); GLint linked=0; glAttachShader(program,vs); glAttachShader(program,fs); glBindAttribLocation(program,0,"p");
    glLinkProgram(program); glGetProgramiv(program,GL_LINK_STATUS,&linked); require(linked,"shader linking"); glUseProgram(program);
    const GLfloat triangle[]={-1,-1,3,-1,-1,3}; glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,0,triangle); glEnableVertexAttribArray(0);
    glDrawArrays(GL_TRIANGLES,0,3); glReadPixels(16,16,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);
    require(glGetError()==GL_NO_ERROR && pixel[0]<5 && pixel[1]>250 && pixel[2]<5,"shader rendered green framebuffer");
    glDeleteProgram(program); glDeleteShader(vs); glDeleteShader(fs);
    eglMakeCurrent(d,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT); eglDestroySurface(d,surface); eglDestroyContext(d,c); eglTerminate(d);
    puts("PASS source shared graphics: Wayland, XKB, EGL and shader pixels"); return 0;
}
